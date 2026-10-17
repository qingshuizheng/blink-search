;;; blink-search-icon-test.el --- Turning a colour into an SVG colour  -*- lexical-binding: t; -*-

;;; Commentary:
;; `blink-search-icon-convert-to-svg-color' is the one piece of the icon code
;; that does not need an SVG file, a graphic display or a frame, so it is the
;; one piece that can be checked in batch Emacs -- and it is also the piece
;; that has to survive a theme whose colours Emacs does not know.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-icon-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-icon)

(ert-deftest blink-search-icon-converts-a-named-color ()
  "A colour Emacs knows becomes the #rrggbb form SVG wants."
  (should (equal (blink-search-icon-convert-to-svg-color "black") "#000000"))
  (should (equal (blink-search-icon-convert-to-svg-color "white") "#ffffff"))
  (should (equal (blink-search-icon-convert-to-svg-color "#ff0000") "#ff0000")))

(ert-deftest blink-search-icon-keeps-an-unknown-color ()
  "A colour Emacs does not know is passed through unchanged.

A theme may name a colour in a way this Emacs cannot parse; the icon then
has to lose that colour rather than the whole menu."
  (should (equal (blink-search-icon-convert-to-svg-color "not-a-colour") "not-a-colour"))
  (should (equal (blink-search-icon-convert-to-svg-color "") "")))

(ert-deftest blink-search-icon-filepath-points-into-the-icon-directory ()
  "The path of an icon is built from `blink-search-icon-dir'."
  (let ((blink-search-icon-dir "/tmp/icons"))
    (should (equal (blink-search-icon-filepath "material" "history")
                   "/tmp/icons/material_history.svg"))))

(ert-deftest blink-search-icon-alist-has-a-fallback ()
  "Every backend name maps to a (COLLECTION NAME COLOUR) triple.

The entry whose key is t is the fallback a backend without an icon of
its own uses."
  (dolist (entry blink-search-icon-alist)
    (should (consp entry))
    (let ((icon (cdr entry)))
      (should (= (length icon) 3))
      (should (stringp (nth 0 icon)))
      (should (stringp (nth 1 icon)))
      (should (stringp (nth 2 icon))))))

(ert-deftest blink-search-icon-build-returns-a-string-without-a-display ()
  "The icon string degrades to an empty string in a terminal."
  (let ((blink-search-enable-icon t))
    ;; `display-graphic-p' is nil in batch Emacs, which is the case the rest
    ;; of the package has to be able to concatenate.
    (should (equal (blink-search-icon-build "material" "history" "#000000") ""))))

(provide 'blink-search-icon-test)
;;; blink-search-icon-test.el ends here
