;;; blink-search-navigate-test.el --- What each key asks the search to do  -*- lexical-binding: t; -*-

;;; Commentary:
;; The movement commands are thin on purpose: the Python half owns the
;; selection, and Elisp only says which way to move.  Thin is exactly why they
;; need a test -- a command that asks for the wrong method, or that forgets to
;; leave the search before it runs an action, fails in a way the user sees as
;; "the key does nothing".
;;
;; The calls into Python are captured instead of sent, so the tests check the
;; method name and the arguments each command sends.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-navigate-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-navigate)

(defvar blink-search-navigate-test--calls nil
  "The (METHOD ARGS...) of every call the commands made.")

(defmacro blink-search-navigate-test--with-calls (&rest body)
  "Run BODY with the calls into Python captured in the test variable."
  `(let ((blink-search-navigate-test--calls nil))
     (cl-letf (((symbol-function 'blink-search-call-async)
                (lambda (method &rest args)
                  (push (cons method args) blink-search-navigate-test--calls))))
       ,@body)
     (nreverse blink-search-navigate-test--calls)))

(defun blink-search-navigate-test--candidate (backend text)
  "Build one candidate row of BACKEND whose text is TEXT."
  (list :backend backend :candidate text))

(ert-deftest blink-search-navigate-movement-asks-the-right-method ()
  "Each movement command names the method the Python half listens for."
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-candidate-select-next))
                 '(("select_next_candidate_item"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-candidate-select-prev))
                 '(("select_prev_candidate_item"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-backend-select-next))
                 '(("select_next_backend_item"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-backend-select-prev))
                 '(("select_prev_backend_item"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-candidate-group-select-next))
                 '(("select_next_candidate_group"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-candidate-group-select-prev))
                 '(("select_prev_candidate_group")))))

(ert-deftest blink-search-navigate-preview-moves-then-previews ()
  "Previewing the next candidate moves the selection before it shows it."
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-preview-next))
                 '(("select_next_candidate_item") ("select_candidate_item"))))
  (should (equal (blink-search-navigate-test--with-calls
                  (blink-search-preview-prev))
                 '(("select_prev_candidate_item") ("select_candidate_item")))))

(ert-deftest blink-search-navigate-an-action-carries-backend-and-candidate ()
  "Running an action sends the backend name and the text of the candidate."
  (let ((blink-search-candidate-items
         (list (blink-search-navigate-test--candidate "Find File" "README.md")
               (blink-search-navigate-test--candidate "Find File" "core/utils.py")))
        (blink-search-candidate-select-index 1)
        (blink-search-backend-items nil)
        (blink-search-backend-select-index 0)
        (blink-search-backend-buffer " *blink search backend*")
        (blink-search-window-configuration nil))
    (should (equal (blink-search-navigate-test--with-calls
                    (blink-search-do))
                   '(("clean") ("search_do" "Find File" "core/utils.py"))))))

(ert-deftest blink-search-navigate-a-structured-candidate-gives-up-its-text ()
  "A candidate that came from ripgrep is sent as its text."
  (let ((blink-search-candidate-items
         (list (list :backend "Grep File"
                     :candidate '(:text "core/utils.py:12:3: def parse" :matches ((20 23))))))
        (blink-search-candidate-select-index 0)
        (blink-search-backend-items nil)
        (blink-search-backend-select-index 0)
        (blink-search-backend-buffer " *blink search backend*")
        (blink-search-window-configuration nil))
    (should (equal (blink-search-navigate-test--with-calls
                    (blink-search-copy))
                   '(("clean") ("search_copy" "Grep File" "core/utils.py:12:3: def parse"))))))

(ert-deftest blink-search-navigate-an-action-on-an-empty-menu-does-nothing ()
  "A key pressed before any candidate arrived is not an error."
  (let ((blink-search-candidate-items nil)
        (blink-search-window-configuration nil))
    (should (null (blink-search-navigate-test--with-calls
                   (blink-search-do))))))

(ert-deftest blink-search-navigate-continue-keeps-the-search-open ()
  "Continuing a search does not leave the menu, it searches again."
  (let ((blink-search-candidate-items
         (list (blink-search-navigate-test--candidate "Find File" "core")))
        (blink-search-candidate-select-index 0)
        (blink-search-backend-items nil)
        (blink-search-backend-select-index 0)
        (blink-search-backend-buffer " *blink search backend*")
        (blink-search-window-configuration nil))
    (should (equal (blink-search-navigate-test--with-calls
                    (blink-search-continue))
                   '(("search_continue" "Find File" "core"))))))

(ert-deftest blink-search-navigate-quick-do-resolves-the-pressed-key ()
  "A quick key picks the candidate at the position of the key in the list."
  (let ((blink-search-candidate-items
         (list (blink-search-navigate-test--candidate "Find File" "first.md")
               (blink-search-navigate-test--candidate "Find File" "second.md")))
        (blink-search-quick-keys '("x" "y"))
        (blink-search-window-configuration nil))
    (let ((last-command-event ?y))
      (should (equal (blink-search-navigate-test--with-calls
                      (blink-search-quick-do))
                     '(("clean") ("search_do" "Find File" "second.md")))))))

(ert-deftest blink-search-navigate-quick-do-ignores-a-key-past-the-end ()
  "A quick key with no candidate behind it does nothing."
  (let ((blink-search-candidate-items
         (list (blink-search-navigate-test--candidate "Find File" "only.md")))
        (blink-search-quick-keys '("x" "y"))
        (blink-search-window-configuration nil))
    (let ((last-command-event ?y))
      (should (null (blink-search-navigate-test--with-calls
                     (blink-search-quick-do)))))))

(ert-deftest blink-search-navigate-goto-column-counts-characters ()
  "The column jump lands on the character, not on the byte."
  (with-temp-buffer
    (insert "中abc\n")
    (goto-char (point-min))
    (blink-search-goto-column 0)
    (should (= (point) (point-min)))
    (blink-search-goto-column 3)
    ;; byte 3 is where the Chinese character ends, so point is after it
    (should (= (point) (1+ (point-min)))))
  (with-temp-buffer
    (insert "abcdef\n")
    (goto-char (point-min))
    (blink-search-goto-column 3)
    (should (= (point) (+ (point-min) 3)))))


;;; The wire convention of a call into Python.

(ert-deftest blink-search-call-async-passes-a-flat-argument-list ()
  "The arguments reach `call-deferred' as one flat list.

`blink-search-epc-call-deferred' writes `(call UID METHOD ARGS)' and
python-epc spreads ARGS into the method's parameters.  Wrapping the list once
more -- `(list args)' -- makes `search' receive its three arguments as one,
and the search process answers that two required positional arguments are
missing.  That is a mistake that only shows up against the real Python half,
so it is pinned here on the Elisp side."
  (let (captured)
    (cl-letf (((symbol-function 'blink-search-epc-live-p) (lambda (&rest _) t))
              ((symbol-function 'blink-search-epc-call-deferred)
               (lambda (_mngr method args) (setq captured (cons method args)))))
      (blink-search-call-async "search" "blink" 10 '("Buffer List")))
    (should (equal (car captured) 'search))
    (should (equal (cdr captured) '("blink" 10 ("Buffer List"))))
    ;; and not one element holding the list
    (should (= (length (cdr captured)) 3))))

(ert-deftest blink-search-call-async-keeps-a-list-argument-a-list ()
  "An argument that is itself a list stays one argument of that type."
  (let (captured)
    (cl-letf (((symbol-function 'blink-search-epc-live-p) (lambda (&rest _) t))
              ((symbol-function 'blink-search-epc-call-deferred)
               (lambda (_mngr method args) (setq captured (cons method args)))))
      (blink-search-call-async "search_elisp_symbol_update" '("a" "b")))
    (should (equal (cdr captured) '(("a" "b"))))))


(ert-deftest blink-search-quit-forgets-the-old-candidates ()
  "Leaving the search clears what the menu was showing.

The buffers are erased when the menu opens, but the variables that hold the
candidates outlive it.  A key pressed after reopening, before the first new
candidate arrives, would otherwise act on a candidate of the previous
search -- opening a file the user did not select in this one."
  (let ((blink-search-candidate-items (list '(:backend "Find File" :candidate "old.md")))
        (blink-search-candidate-select-index 0)
        (blink-search-backend-items (list "old.md"))
        (blink-search-backend-select-index 0)
        (blink-search-backend-name "Find File")
        (blink-search-item-index 1)
        (blink-search-items-number 1)
        (blink-search-backend-number 1)
        (blink-search-window-configuration nil))
    (cl-letf (((symbol-function 'blink-search-call-async) #'ignore))
      (blink-search-quit))
    (should-not blink-search-candidate-items)
    (should-not blink-search-candidate-select-index)
    (should-not blink-search-backend-items)
    (should-not blink-search-backend-select-index)
    (should-not blink-search-backend-name)
    (should-not blink-search-item-index)
    (should-not blink-search-items-number)
    (should-not blink-search-backend-number)))

(provide 'blink-search-navigate-test)
;;; blink-search-navigate-test.el ends here
