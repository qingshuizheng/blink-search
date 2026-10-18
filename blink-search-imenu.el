;;; blink-search-imenu.el --- IMenu backend for blink-search   -*- lexical-binding: t; -*-

;; Filename: blink-search-imenu.el
;; Description: IMenu backend for blink-search
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Created: 2022-11-04 08:41:34
;; Version: 0.1
;; Last-Updated: 2022-11-04 08:41:34
;;           By: Andy Stewart
;; URL: https://www.github.org/manateelazycat/blink-search-imenu
;; Keywords:
;; Compatibility: GNU Emacs 28.2
;;
;; Features that might be required by this library:
;;
;;
;;

;;; This file is NOT part of GNU Emacs

;;; License
;;
;; This program is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation; either version 3, or (at your option)
;; any later version.

;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with this program; see the file COPYING.  If not, write to
;; the Free Software Foundation, Inc., 51 Franklin Street, Fifth
;; Floor, Boston, MA 02110-1301, USA.

;;; Commentary:
;;
;; IMenu backend for blink-search
;;

;;; Installation:
;;
;; Put blink-search-imenu.el to your load-path.
;; The load-path is usually ~/elisp/.
;; It's set in your ~/.emacs like this:
;; (add-to-list 'load-path (expand-file-name "~/elisp"))
;;
;; And the following to your ~/.emacs startup file.
;;
;; (require 'blink-search-imenu)
;;
;; No need more.

;;; Customize:
;;
;;
;;
;; All of the above can customize by:
;;      M-x customize-group RET blink-search-imenu RET
;;

;;; Change log:
;;
;; 2022/11/04
;;      * First released.
;;

;;; Acknowledgements:
;;
;;
;;

;;; TODO
;;
;;
;;

;;; Require

;;; Code:

(require 'imenu)
(require 'blink-search-state)
(require 'blink-search-process)
(require 'blink-search-navigate)

(defvar blink-search-imenu-buffer nil
  "The buffer the index in the Python half was built from.
`blink-search-start-buffer' is cleared when the menu is left, and the jump
below runs after that: the position it is given belongs to this buffer, so
the buffer is remembered here.
`blink-search-start-buffer` is cleared by `blink-search-quit'.")

(defun blink-search-init-imenu ()
  "Push the imenu candidates of the start buffer to the Python half."
  (when (blink-search-epc-live-p blink-search-epc-process)
    (setq blink-search-imenu-buffer blink-search-start-buffer)
    (with-current-buffer blink-search-start-buffer
      (let ((candidates (blink-search-imenu-get-candidates)))
        (when candidates (blink-search-call-async "search_imenu_update" candidates))))))

(defun blink-search-imenu-get-candidates ()
  "Return the imenu index of the start buffer as a list of candidates.
Each candidate is a list of the name of the entry and the position it
points at.  Return nil when the buffer has no imenu index at all."
  (ignore-errors
    (mapcar (lambda (info) (list (car info) (marker-position (cdr info))))
            (let* ((index (ignore-errors (imenu--make-index-alist t))))
              (when index
                (blink-search-imenu-build-candidates
                 (delete (assoc "*Rescan*" index) index)))))))

(defun blink-search-imenu-build-candidates (alist)
  "Flatten the imenu ALIST into a list of (NAME . POSITION) candidates.
The Types and Variables groups are dropped: they are a
subdivision of a language's index, not something a user searches for
by name.  Markers and overlays are copied, because the index alist is
rebuilt on every search while the candidates outlive it."
  (cl-remove-if
   (lambda (c)
     (or (string-equal (car c) "Types")
         (string-equal (car c) "Variables")))
   (cl-loop for elm in alist
            nconc (cond
                   ((imenu--subalist-p elm)
                    (blink-search-imenu-build-candidates
                     (cl-loop for (e . v) in (cdr elm) collect
                              (cons
                               e
                               (if (integerp v) (copy-marker v) v)))))
                   ((listp (cdr elm))
                    (and elm (list elm)))
                   (t
                    (and (cdr elm)
                         (setcdr elm (pcase (cdr elm)
                                       ((and ov (pred overlayp))
                                        (copy-overlay ov))
                                       ((and mk (or (pred markerp)
                                                    (pred integerp)))
                                        (copy-marker mk))))
                         (list elm)))))))

(defun blink-search-imenu-do (point)
  "Jump to POINT in the buffer the index came from and flash the line.
POINT is a position in that buffer, not in whatever buffer happens to be
current when the answer arrives -- the menu has already been left, and the
current buffer at that moment is the input buffer.  Jumping there put the
point in the middle of the menu instead of on the definition."
  (let* ((remembered (and (buffer-live-p blink-search-imenu-buffer)
                          blink-search-imenu-buffer))
         (buffer (or remembered
                     ;; No buffer was remembered: the position belongs to
                     ;; whatever buffer it fits in, which is the current one
                     ;; for a caller that passes a position of its own.
                     (if (and (integer-or-marker-p point)
                              (<= (point-min) point (point-max)))
                         (current-buffer)
                       (window-buffer (selected-window))))))
    (with-current-buffer buffer
      (goto-char (min (max point (point-min)) (point-max)))
      (blink-search-flash-locate))))

(add-to-list 'blink-search-start-update-list #'blink-search-init-imenu t)

(provide 'blink-search-imenu)
;;; blink-search-imenu.el ends here
