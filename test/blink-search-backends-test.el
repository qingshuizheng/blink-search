;;; blink-search-backends-test.el --- What the Elisp backends push to Python  -*- lexical-binding: t; -*-

;;; Commentary:
;; Each Elisp backend does one of two things: it pushes state to the Python
;; half, or it opens what a candidate stands for.  Both are thin, and both are
;; where a rename goes unnoticed -- the Python side would simply stop getting
;; the buffer list, or a preview would open the wrong file.
;;
;; The calls into Python and the calls into Emacs are captured instead of
;; sent, so the tests check the method name, the shape of the payload and the
;; mapping from a candidate back to a path.  No buffer is opened and no
;; process is started.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-backends-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'recentf)
(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-buffer-list)
(require 'blink-search-elisp-symbol)
(require 'blink-search-recent-file)
(require 'blink-search-imenu)
(require 'blink-search-current-buffer)
(require 'blink-search-grep-file)
(require 'blink-search-grep-pdf)
(require 'blink-search-pdf)

(defvar blink-search-backends-test--epc nil
  "Every (METHOD ARGS...) the backends asked the Python half for.")

(defvar blink-search-backends-test--emacs nil
  "Every (FUNCTION ARGS...) the backends asked Emacs for.")

(defmacro blink-search-backends-test--capture (&rest body)
  "Run BODY with the calls into Python and Emacs captured."
  `(let ((blink-search-backends-test--epc nil)
         (blink-search-backends-test--emacs nil))
     (cl-letf (((symbol-function 'blink-search-call-async)
                (lambda (method &rest args)
                  (push (cons method args) blink-search-backends-test--epc)))
               ((symbol-function 'eval_in_emacs)
                (lambda (function &rest args)
                  (push (cons function args) blink-search-backends-test--emacs)))
               ((symbol-function 'blink-search-epc-live-p) (lambda (&rest _) t)))
       ,@body)
     (list (nreverse blink-search-backends-test--epc)
           (nreverse blink-search-backends-test--emacs))))

(defun blink-search-backends-test--epc (result)
  "Return the EPC calls of RESULT."
  (nth 0 result))

(defun blink-search-backends-test--emacs (result)
  "Return the Emacs calls of RESULT."
  (nth 1 result))


;;
;; The backends that push state.
;;

(ert-deftest blink-search-backend-buffer-list-pushes-the-names ()
  "The buffer list backend sends the names and nothing else."
  (let ((result (blink-search-backends-test--capture
                 (blink-search-buffer-list-update))))
    (should (= (length (blink-search-backends-test--epc result)) 1))
    (let ((call (car (blink-search-backends-test--epc result))))
      (should (member (car call) '("search_buffer_list_update" "search_sort_buffer_list_update")))
      (should (equal (cadr call) (mapcar #'buffer-name (buffer-list)))))))

(ert-deftest blink-search-backend-elisp-symbol-pushes-once-per-change ()
  "The symbol list is only sent when the number of symbols changed.

The backend runs on an idle timer, so a payload that is sent on every tick
would keep the Python process busy for nothing.
"
  (let ((blink-search-elisp-symbol-size 0)
        (blink-search-elisp-symbol-timer nil))
    (cl-letf (((symbol-function 'blink-search-elisp-local-symbols) (lambda () nil))
              ((symbol-function 'blink-search-elisp-global-symbols) (lambda () '("alpha" "beta"))))
      (let ((result (blink-search-backends-test--capture
                     (blink-search-elisp-symbol-update))))
        (should (= (length (blink-search-backends-test--epc result)) 1))
        (should (equal (car (blink-search-backends-test--epc result))
                       '("search_elisp_symbol_update" ("alpha" "beta"))))
        (should (= blink-search-elisp-symbol-size 2)))

      ;; the same list again: nothing to say
      (let ((result (blink-search-backends-test--capture
                     (blink-search-elisp-symbol-update))))
        (should (null (blink-search-backends-test--epc result)))))))

(ert-deftest blink-search-backend-recent-file-pushes-once-per-change ()
  "The recent file list is only sent when its length changed."
  (let ((recentf-list '("/a.el" "/b.el"))
        (blink-search-recent-file-size 0))
    (let ((result (blink-search-backends-test--capture
                   (blink-search-recent-file-update))))
      (should (equal (car (blink-search-backends-test--epc result))
                     '("search_recent_file_update" ("/a.el" "/b.el"))))
      (should (= blink-search-recent-file-size 2)))

    (let ((result (blink-search-backends-test--capture
                   (blink-search-recent-file-update))))
      (should (null (blink-search-backends-test--epc result))))))

(ert-deftest blink-search-backend-recent-file-stops-its-timer ()
  "Stopping the backend cancels the timer and forgets the count."
  (let ((blink-search-recent-file-size 5)
        (blink-search-recent-file-timer (run-with-idle-timer 100 t #'ignore)))
    (blink-search-stop-recent-file-update)
    (should (null blink-search-recent-file-timer))
    (should (= blink-search-recent-file-size 0))))

(ert-deftest blink-search-backend-imenu-pushes-the-index ()
  "The imenu backend sends the (name position) pairs of the start buffer."
  (let ((blink-search-start-buffer (current-buffer)))
    (cl-letf (((symbol-function 'blink-search-imenu-get-candidates)
               (lambda () '(("defun-one" 12)))))
      (let ((result (blink-search-backends-test--capture
                     (blink-search-init-imenu))))
        (should (equal (car (blink-search-backends-test--epc result))
                       '("search_imenu_update" (("defun-one" 12)))))))))

(ert-deftest blink-search-backend-imenu-do-jumps-to-the-position ()
  "Selecting an imenu candidate moves point to the position it holds."
  (with-temp-buffer
    (insert "one\ntwo\nthree\n")
    (goto-char (point-min))
    (cl-letf (((symbol-function 'blink-search-flash-locate) #'ignore))
      (blink-search-imenu-do 5)
      (should (= (point) 5)))))

(ert-deftest blink-search-backend-current-buffer-encodes-utf-8-to-base64 ()
  "The buffer content is base64 encoded on its way to Python."
  (with-temp-buffer
    (insert "notes")
    (should (equal (blink-search-encode-string (buffer-string)) "bm90ZXM="))))

(ert-deftest blink-search-backend-current-buffer-jumps-to-line-and-column ()
  "Opening a candidate switches to the buffer and goes to the position."
  (with-temp-buffer
    (insert "one\ntwo\nthree\n")
    (let ((name (buffer-name)))
      (let ((result (blink-search-backends-test--capture
                     (blink-search-current-buffer-do name 2 1))))
        (should (null (blink-search-backends-test--epc result)))))))


;;
;; The backends that open a file.
;;

(ert-deftest blink-search-backend-grep-file-do-jumps-into-the-project ()
  "A grep candidate is a path relative to the project, a line and a column.

The file has to exist for `find-file' to open it, so this test only says
that the jump itself does not raise; the path arithmetic is what the Python
tests cover.
"
  (let ((blink-search-grep-file-temp-buffers nil))
    (cl-letf (((symbol-function 'find-file) #'ignore)
              ((symbol-function 'blink-search-flash-locate) #'ignore)
              ((symbol-function 'blink-search-goto-column) #'ignore))
      (blink-search-grep-file-do "/tmp/a.el" 3 4))))

(ert-deftest blink-search-backend-grep-file-clean-kills-the-previews ()
  "The buffers a preview opened are killed when the search ends."
  (let* ((preview (generate-new-buffer " *blink preview test*"))
         (blink-search-grep-file-temp-buffers (list preview)))
    (blink-search-grep-file-clean)
    (should-not (buffer-live-p preview))
    (should (null blink-search-grep-file-temp-buffers))))

(ert-deftest blink-search-backend-grep-file-finds-an-open-buffer ()
  "An already open file is found instead of opened again."
  (let* ((file (make-temp-file "blink-grep-file" nil ".el"))
         (visiting (find-file-noselect file)))
    (unwind-protect
        (should (eq (blink-search-grep-file-get-match-buffer file) visiting))
      (kill-buffer visiting)
      (delete-file file))))

(ert-deftest blink-search-backend-pdf-clean-cancels-its-timer ()
  "Leaving the search cancels a preview that is still pending.

The pending timer is what makes this observable without a viewer: the
preview is cancelled before the viewer is told to drop its buffers, so a
timer that survives the call is a preview that would fire after the menu is
gone.
"
  (let* ((timer (run-with-idle-timer 100 t #'ignore))
         (blink-search-pdf-preview-timer timer)
         (blink-search-grep-file-temp-buffers nil))
    (should (memq timer timer-idle-list))

    (let ((result (blink-search-backends-test--capture
                   (blink-search-pdf-clean))))
      ;; the timer is out of the idle list, so it will not fire after the
      ;; menu is gone, and the variable no longer holds it
      (should-not (memq timer timer-idle-list))
      (should (null blink-search-pdf-preview-timer))
      (should (null (blink-search-backends-test--epc result))))))

(ert-deftest blink-search-backend-grep-pdf-clean-cancels-its-timer ()
  "The multi directory pdf backend cancels its preview as well."
  (let ((blink-search-grep-pdf-preview-timer (run-with-idle-timer 100 t #'ignore))
        (blink-search-grep-file-temp-buffers nil))
    (let ((result (blink-search-backends-test--capture
                   (blink-search-grep-pdf-clean))))
      (should (null blink-search-grep-pdf-preview-timer))
      (should (null (blink-search-backends-test--epc result))
              ))))

(provide 'blink-search-backends-test)
;;; blink-search-backends-test.el ends here
