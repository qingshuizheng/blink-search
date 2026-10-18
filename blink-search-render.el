;;; blink-search-render.el --- Draw the blink-search menu  -*- lexical-binding: t; -*-

;; Filename: blink-search-render.el
;; Description: Draw the blink-search menu
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Version: 0.1
;; URL: https://github.com/manateelazycat/blink-search
;; Keywords: tools
;; Compatibility: emacs-version >= 28
;;
;; This file is NOT part of GNU Emacs

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
;; The drawing half of blink-search: it turns the answer of the last search
;; into the three visible buffers (tooltip line, candidate rows, backend rows)
;; and is the only place that writes a face into a buffer.
;;
;; `blink-search-update-items' is the entry point the Python half calls; the
;; candidate and backend buffers are filled by `blink-search-render'.  The
;; measurements (`blink-search-indent-pixel', `blink-search-column-to-string-index')
;; and the candidate shortening are pure functions.

;;; Code:

(require 'blink-search-state)
(require 'blink-search-ui)
(require 'blink-search-icon)

(defun blink-search-get-row-number ()
  "Return how many candidate lines fit in the candidate window."
  (/ (nth 3 (blink-search-get-window-allocation (get-buffer-window blink-search-candidate-buffer))) (line-pixel-height)))

(defsubst blink-search-indent-pixel (xpos)
  "Return a display property that aligns to XPOS."
  `(space :align-to (,xpos)))

(defun blink-search-render-candidate (backend-name candidate candidate-max-length)
  "Return CANDIDATE shortened to CANDIDATE-MAX-LENGTH for BACKEND-NAME.
A file name is shortened to its base name; a line of a file keeps its
head and loses the tail; everything else keeps both ends around an
ellipsis, because the tail of a path or of a symbol is what tells two
candidates apart."
  (let ((candidate-length (length candidate)))
    (cond ((string-equal backend-name "Recent File")
           (file-name-nondirectory candidate))
          ((member backend-name '("Current Buffer" "Grep File" "Grep PDF" "EAF Browser" "Common Directory" "PDF"))
           (blink-search-truncate-candidate-with-ellipsis candidate candidate-max-length candidate-max-length))
          (t
           (if (<= candidate-length candidate-max-length)
               candidate
             (concat (substring candidate 0 (/ candidate-max-length 2))
                     "..."
                     (substring candidate (- (length candidate) (/ candidate-max-length 2)) (length candidate))))))))

(defun blink-search-truncate-candidate-with-ellipsis (candidate candidate-max-length truncate-length)
  "Return CANDIDATE cut to TRUNCATE-LENGTH characters plus an ellipsis.
CANDIDATE-MAX-LENGTH is accepted for symmetry with
`blink-search-render-candidate' and is not used."
  (ignore candidate-max-length)
  (let ((candidate-length (length candidate)))
    (if (<= candidate-length truncate-length)
        candidate
      (concat (substring candidate 0 (- truncate-length (length "..."))) "..."))))

(defun blink-search-get-candidate-text (candidate-info)
  "Return the text of CANDIDATE-INFO.
CANDIDATE-INFO is either a plain string or a plist with a :text key, as
the Python half sends both shapes."
  ;; Remove ^M char at end of line.
  (replace-regexp-in-string
   "\r+$" ""
   (format
    "%s"
    (if (stringp candidate-info)
        candidate-info
      (plist-get candidate-info :text)))))

(defun blink-search-get-candidate-matches (candidate-info)
  "Return the match positions of CANDIDATE-INFO, or nil.
The positions are byte offsets into the candidate text, as ripgrep
reports them; a plain string candidate has none."
  (unless (stringp candidate-info)
    (plist-get candidate-info :matches)))

(defun blink-search-column-to-string-index (string column)
  "Return the character index inside STRING that starts byte COLUMN.
`move-to-column' cannot do this for a mixed string of Chinese and
English characters, which is what ripgrep reports positions in."
  (let ((scan-column 0)
        (index 0)
        (length (length string)))
    (while (and (> column scan-column) (< index length))
      (setq index (1+ index))
      (setq scan-column (string-bytes (substring string 0 index))))
    index))

(defun blink-search-render-backend-buffer (backend-items backend-select-index window-width backend-number)
  "Fill `blink-search-backend-buffer' with BACKEND-ITEMS.
BACKEND-SELECT-INDEX is the row to highlight, WINDOW-WIDTH the width to
pad each row to, and BACKEND-NUMBER the number of backends that returned
a candidate: the buffer stays empty unless there is more than one."
  (with-current-buffer blink-search-backend-buffer
    (erase-buffer)

    (when (> backend-number 1)
      (let ((backend-index 0))

        (when backend-items
          (dolist (candidate-info backend-items)
            (let* ((candidate (if (stringp candidate-info) candidate-info (plist-get candidate-info :text)))
                   backend-line)

              (setq backend-line
                    (concat
                     (propertize (format " %s " candidate) 'face (if (equal backend-index backend-select-index) 'blink-search-select-face 'font-lock-doc-face))
                     (propertize " " 'display (blink-search-indent-pixel window-width))
                     "\n"))

              (when (equal backend-index backend-select-index)
                (add-face-text-property 0 (length backend-line) 'blink-search-select-face 'append backend-line))

              (insert backend-line)

              (setq backend-index (1+ backend-index)))))))))

(defun blink-search-render-candidate-buffer (candidate-items candidate-select-index window-width backend-number)
  "Fill `blink-search-candidate-buffer' with CANDIDATE-ITEMS.
CANDIDATE-SELECT-INDEX is the row to highlight, WINDOW-WIDTH the width
the rows are padded to, and BACKEND-NUMBER decides whether a row also
shows the name of its backend."
  (with-current-buffer blink-search-candidate-buffer
    (let* ((candidate-max-length (ceiling (* (/ window-width (frame-char-width)) 0.6)))
           (candidate-index 0))
      (erase-buffer)

      (when candidate-items
        (dolist (item candidate-items)
          (let* ((candidate-info (plist-get item :candidate))
                 (candidate (blink-search-get-candidate-text candidate-info))
                 (matches (blink-search-get-candidate-matches candidate-info))
                 (backend (plist-get item :backend))
                 (display-candiate (blink-search-render-candidate backend candidate candidate-max-length))
                 (padding-right 5)
                 (icon (cdr (assoc backend blink-search-icon-alist)))
                 (icon-default (cdr (assoc t blink-search-icon-alist)))
                 (display-icon (if icon icon icon-default))
                 (icon-text (blink-search-icon-build (nth 0 display-icon) (nth 1 display-icon) (nth 2 display-icon)))
                 candidate-prefix
                 candidate-prefix-length
                 candidate-line)

            (setq candidate-prefix
                  (concat
                   icon-text
                   (propertize (format "%s " (nth candidate-index blink-search-quick-keys)) 'face 'font-lock-type-face)))

            (setq candidate-prefix-length (length candidate-prefix))

            (setq candidate-line
                  (concat
                   candidate-prefix
                   (if (> backend-number 1)
                       (format "%s " display-candiate)
                     (format "%s " candidate))
                   (if (> backend-number 1)
                       (propertize " " 'display
                                   (blink-search-indent-pixel
                                    (- window-width
                                       (if (fboundp 'string-pixel-width)
                                           (string-pixel-width (format "%s%s" (make-string 2 ?\s) backend))
                                         (* (frame-char-width) (+ (string-width backend) padding-right))))))
                     (propertize " " 'display (blink-search-indent-pixel window-width)))
                   (when (> backend-number 1)
                     (propertize (format "%s " backend)
                                 'face (if (equal candidate-index candidate-select-index) 'blink-search-select-face 'font-lock-doc-face)))
                   "\n"))

            ;; Highlight match strings.
            (when (and matches
                       (equal backend-number 1))
              (dolist (match matches)
                (let* ((line-text (substring candidate-line candidate-prefix-length))
                       (match-start-point (+ (blink-search-column-to-string-index line-text (nth 0 match))
                                             candidate-prefix-length))
                       (match-end-point (+ (blink-search-column-to-string-index line-text (nth 1 match))
                                           candidate-prefix-length)))
                  (add-face-text-property match-start-point match-end-point 'font-lock-type-face 'append candidate-line))))

            (when (equal candidate-index candidate-select-index)
              (add-face-text-property 0 (length candidate-line) 'blink-search-select-face 'append candidate-line))

            (insert candidate-line)

            (setq candidate-index (1+ candidate-index))))))))

(defun blink-search-render-tooltip-buffer (backend-name search-items-index search-items-number)
  "Fill `blink-search-tooltip-buffer' with the search prefix help line.
BACKEND-NAME is the backend of the selected row, SEARCH-ITEMS-INDEX
the one based index of that row and SEARCH-ITEMS-NUMBER the number of
candidates the search found."
  (with-current-buffer blink-search-tooltip-buffer
    (erase-buffer)
    (insert
     (concat
      (propertize (format "%s [%s/%s]" backend-name search-items-index search-items-number)
                  'face 'font-lock-constant-face)
      (propertize " search prefix: " 'face 'font-lock-type-face)
      (propertize "#" 'face 'font-lock-type-face)
      (propertize " buffer " 'face 'font-lock-keyword-face)
      (propertize "!" 'face 'font-lock-type-face)
      (propertize " directory " 'face 'font-lock-keyword-face)
      (propertize ";" 'face 'font-lock-type-face)
      (propertize " pdfs " 'face 'font-lock-keyword-face)
      (propertize ":" 'face 'font-lock-type-face)
      (propertize " pdf " 'face 'font-lock-keyword-face)))))

(defun blink-search-render ()
  "Draw the tooltip, candidate and backend buffers from the current state.
The state it reads is the group of buffer local variables
`blink-search-update-items' has just set; the function itself is called
every time the selection moves, so it has to be cheap."
  (let ((candidate-items blink-search-candidate-items)
        (candidate-select-index blink-search-candidate-select-index)
        (backend-items blink-search-backend-items)
        (backend-select-index blink-search-backend-select-index)
        (backend-name blink-search-backend-name)
        (search-items-index blink-search-item-index)
        (search-items-number blink-search-items-number)
        (backend-number blink-search-backend-number))
    (save-excursion
      (let* ((window-allocation (blink-search-get-window-allocation (get-buffer-window blink-search-candidate-buffer)))
             (window-width (nth 2 window-allocation)))
        (blink-search-render-tooltip-buffer backend-name search-items-index search-items-number)
        (blink-search-render-candidate-buffer candidate-items candidate-select-index window-width backend-number)
        (blink-search-render-backend-buffer backend-items backend-select-index window-width backend-number)))))

(defun blink-search-update-items (candidate-items
                                  candidate-select-index
                                  backend-items backend-select-index backend-name
                                  search-items-index search-items-number backend-number)
  "Render the answer of the search that just finished.

CANDIDATE-ITEMS are the rows to show, CANDIDATE-SELECT-INDEX the
selected row, BACKEND-ITEMS the candidates of the backend that owns the
selection, BACKEND-SELECT-INDEX the selected row inside those,
BACKEND-NAME the name of that backend, SEARCH-ITEMS-INDEX and
SEARCH-ITEMS-NUMBER the position of the selection in the whole answer,
and BACKEND-NUMBER how many backends returned a candidate.

The Python half calls this; nothing is drawn when the user has already
left the search."
  ;; Don't pop completion candidates when
  (when (get-buffer-window blink-search-input-buffer)
    (setq blink-search-candidate-items candidate-items)
    (setq blink-search-candidate-select-index candidate-select-index)
    (setq blink-search-backend-items backend-items)
    (setq blink-search-backend-select-index backend-select-index)
    (setq blink-search-backend-name backend-name)
    (setq blink-search-item-index search-items-index)
    (setq blink-search-items-number search-items-number)
    (setq blink-search-backend-number backend-number)

    (if (> backend-number 1)
        (blink-search-show-backend-window)
      (blink-search-hide-backend-window))

    (blink-search-render)))

(provide 'blink-search-render)
;;; blink-search-render.el ends here
