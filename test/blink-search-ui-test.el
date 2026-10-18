;;; blink-search-ui-test.el --- Colour arithmetic and window measuring  -*- lexical-binding: t; -*-

;;; Commentary:
;; `blink-search-color-blend' is the one piece of arithmetic in the UI code,
;; so it is also the one piece that fails silently when it is wrong: a wrong
;; blend does not raise, it just makes the selected candidate unreadable.
;;
;; The window measuring helpers are checked against a batch frame, where the
;; numbers are the frame's rather than a user's, but they still have to be
;; consistent: a width that is not positive would make the menu render
;; nothing at all.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-ui-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-ui)
(require 'blink-search-render)

(ert-deftest blink-search-color-blend-mixes-two-colors ()
  "A blend of 0.5 of two colors lands halfway between them."
  (should (equal (blink-search-color-blend "#000000" "#ffffff" 1.0) "#000000"))
  (should (equal (blink-search-color-blend "#000000" "#ffffff" 0.0) "#ffffff"))
  ;; 0x7fff.8 rounds up, so the middle of black and white is 0x80 and not
  ;; 0x7f; the test says so because the difference is visible in a menu.
  (should (equal (blink-search-color-blend "#000000" "#ffffff" 0.5) "#808080")))

(ert-deftest blink-search-color-blend-accepts-named-colors ()
  "A named colour is accepted as well as a hex string."
  (should (equal (blink-search-color-blend "black" "white" 1.0) "#000000"))
  (should (equal (blink-search-color-blend "black" "white" 0.0) "#ffffff")))

(ert-deftest blink-search-get-window-allocation-returns-four-numbers ()
  "The window allocation is (X Y WIDTH HEIGHT), with a positive width."
  (let ((allocation (blink-search-get-window-allocation (selected-window))))
    (should (= (length allocation) 4))
    (should (> (nth 2 allocation) 0))
    (should (> (nth 3 allocation) 0))))

(ert-deftest blink-search-indent-pixel-is-a-display-spec ()
  "An indent is a display property, not a string of spaces."
  (should (equal (blink-search-indent-pixel 42) '(space :align-to (42))))
  ;; The returned form is the value of a `display' property, so it is a
  ;; list whose second element is the alignment it asks for.
  (should (equal (nth 1 (blink-search-indent-pixel 7)) :align-to)))

(ert-deftest blink-search-disable-options-hides-the-mode-line ()
  "The search buffers have no mode line, header line or line numbers."
  (with-temp-buffer
    (blink-search-disable-options)
    (should (null mode-line-format))
    (should (null header-line-format))
    (should (null display-line-numbers))))

(provide 'blink-search-ui-test)
;;; blink-search-ui-test.el ends here

;;; The parent of the popup frame.

(ert-deftest blink-search-posframe-parent-avoids-the-stale-posframe ()
  "The parent is never the posframe itself.

`posframe-show' refuses a frame that is its own parent, and the posframe of
an earlier session is hidden rather than killed, so it can still be the
selected frame when the menu opens again."
  (let ((blink-search-posframe-frame 'stale)
        (blink-search-posframe-emacs-frame 'stale))
    (cl-letf (((symbol-function 'framep) (lambda (&rest _) t))
              ((symbol-function 'frame-live-p) (lambda (&rest _) t))
              ;; `stale' is the popup, recognised by its frame parameter even
              ;; though it is the remembered frame as well
              ((symbol-function 'frame-parameter)
               (lambda (frame parameter)
                 (and (eq parameter 'posframe-buffer)
                      (eq frame 'stale)
                      (cons blink-search-input-buffer (get-buffer-create " *stale*")))))
              ((symbol-function 'selected-frame) (lambda () 'stale))
              ((symbol-function 'frame-list) (lambda () '(stale real))))
      (should (eq (blink-search-posframe-parent-frame) 'real)))))

(ert-deftest blink-search-posframe-parent-prefers-the-starting-frame ()
  "The frame the menu was started from is used when it is still alive."
  (let ((blink-search-posframe-frame 'stale)
        (blink-search-posframe-emacs-frame 'origin))
    (cl-letf (((symbol-function 'frame-live-p) (lambda (&rest _) t))
              ((symbol-function 'frame-parameter) (lambda (&rest _) nil))
              ((symbol-function 'selected-frame) (lambda () 'stale))
              ((symbol-function 'frame-list) (lambda () '(stale origin))))
      (should (eq (blink-search-posframe-parent-frame) 'origin)))))

(ert-deftest blink-search-posframe-show-passes-the-parent ()
  "The parent is handed to `posframe-show' rather than left to it."
  (let (captured)
    (cl-letf (((symbol-function 'posframe-show)
               (lambda (&rest args) (setq captured args) 'popup)))
      (blink-search-posframe-show (get-buffer-create " *blink-search-test*") 'origin))
    ;; the first element is the buffer, so the plist starts after it
    (should (eq (plist-get (cdr captured) :parent-frame) 'origin))))

(ert-deftest blink-search-bind-quit-keys-makes-c-g-leave-the-search ()
  "Every pane of the menu answers `C-g' with the quit command.

A preview can leave the focus in the candidate or backend pane, where `C-g'
used to be `keyboard-quit': it beeped and the popup stayed on screen.
`q' is only bound when the caller asks for it, because in the input buffer
it has to stay a letter."
  (let ((buffer (generate-new-buffer " *blink-search-quit-keys*")))
    (unwind-protect
        (progn
          (blink-search-bind-quit-keys buffer)
          (with-current-buffer buffer
            (should (eq (key-binding (kbd "C-g")) 'blink-search-quit))
            (should (eq (key-binding (kbd "ESC ESC ESC")) 'blink-search-quit))
            (should-not (eq (key-binding (kbd "q")) 'blink-search-quit)))
          (blink-search-bind-quit-keys buffer t)
          (with-current-buffer buffer
            (should (eq (key-binding (kbd "q")) 'blink-search-quit))))
      (kill-buffer buffer))))

(ert-deftest blink-search-posframe-p-recognises-the-popup-by-its-parameter ()
  "A popup is recognised even when its frame variable is nil.

`blink-search-quit' forgets the frame, and a frame it no longer names was
then taken for a real one -- as a parent for the popup itself, which
`posframe-show' refuses it as a circular parent."
  (let ((blink-search-input-buffer " *blink-search-test-input*"))
    (cl-letf (((symbol-function 'framep) (lambda (&rest _) t))
              ((symbol-function 'frame-live-p) (lambda (&rest _) t))
              ((symbol-function 'frame-parameter)
               (lambda (_frame parameter)
                 (and (eq parameter 'posframe-buffer)
                      (cons blink-search-input-buffer
                            (get-buffer-create " *blink-search-test-parent*"))))))
      (should (blink-search-posframe-p 'a-child-frame)))))

(ert-deftest blink-search-select-frame-guard-goes-to-the-parent ()
  "Selecting a hidden popup selects its parent instead."
  (let ((blink-search-input-buffer " *blink-search-test-input*")
        selected)
    (cl-letf (((symbol-function 'framep) (lambda (&rest _) t))
              ((symbol-function 'frame-live-p) (lambda (&rest _) t))
              ((symbol-function 'frame-visible-p) (lambda (&rest _) nil))
              ((symbol-function 'frame-parent) (lambda (&rest _) 'the-main-frame))
              ((symbol-function 'frame-parameter)
               (lambda (_frame parameter)
                 (and (eq parameter 'posframe-buffer)
                      (cons blink-search-input-buffer
                            (get-buffer-create " *blink-search-test-parent*")))))
              ((symbol-function 'select-frame-set-input-focus)
               (lambda (frame &rest _) (setq selected frame))))
      (blink-search-select-frame-guard #'select-frame-set-input-focus 'popup))
    (should (eq selected 'the-main-frame))))

(ert-deftest blink-search-select-frame-guard-leaves-other-frames-alone ()
  "A frame that is not a hidden popup is selected as asked."
  (let ((blink-search-input-buffer " *blink-search-test-input*")
        selected)
    (cl-letf (((symbol-function 'framep) (lambda (&rest _) t))
              ((symbol-function 'frame-live-p) (lambda (&rest _) t))
              ((symbol-function 'frame-visible-p) (lambda (&rest _) t))
              ((symbol-function 'frame-parameter) (lambda (&rest _) nil))
              ((symbol-function 'select-frame-set-input-focus)
               (lambda (frame &rest _) (setq selected frame))))
      (blink-search-select-frame-guard #'select-frame-set-input-focus 'real-frame))
    (should (eq selected 'real-frame))))
