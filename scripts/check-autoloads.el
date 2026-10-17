;;; check-autoloads.el --- check where the entry command is autoloaded from  -*- lexical-binding: t -*-
;;; Commentary:
;; The package ships an autoloads file, so `blink-search' is loaded on the
;; first key press rather than at startup.  Which file that autoload names is
;; therefore part of the contract: it has to be `blink-search.el', the file
;; that requires every module.  An autoload that names a module loads that
;; module alone, and then the keymap it installs names commands nothing has
;; defined -- `C-g' answers "wrong-type-argument commandp
;; blink-search-quit", which looks like a missing `(interactive)' and is not.
;;; Code:

(require 'loaddefs)

(defconst blink-search-autoloads-check-file
  (expand-file-name "blink-search-autoloads-check.el" default-directory)
  "Where the autoloads are generated for the check, then deleted.")

(defun blink-search-check-autoloads ()
  "Signal an error when the entry command is not autoloaded from the entry file."
  (unwind-protect
      (progn
        (loaddefs-generate default-directory blink-search-autoloads-check-file)
        (load blink-search-autoloads-check-file nil t)
        (let ((definition (symbol-function 'blink-search)))
          (unless (autoloadp definition)
            (error "Blink-search is not an autoload after loading the autoloads"))
          (unless (string= (nth 1 definition) "blink-search")
            (error "Blink-search is autoloaded from %S; it has to be autoloaded from blink-search.el"
                   (nth 1 definition))))
        (princ "the entry command is autoloaded from blink-search.el\n"))
    (when (file-exists-p blink-search-autoloads-check-file)
      (delete-file blink-search-autoloads-check-file))))

(blink-search-check-autoloads)

;;; check-autoloads.el ends here
