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
