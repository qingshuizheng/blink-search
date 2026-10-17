;;; blink-search-ui.el --- Windows, faces and icons of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-ui.el
;; Description: Windows, faces and icons of blink-search
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
;; The window layout of a search session and the visual details of it: the
;; bottom split layout, the posframe popup layout, the colours derived from
;; the current theme, and the helpers that measure a window.
;;
;; The layout functions are called by `blink-search' (in blink-search.el) and
;; by `blink-search-quit'; nothing in here talks to the Python process.

;;; Code:

(require 'cl-lib)
(require 'blink-search-state)
(require 'blink-search-process)
(require 'posframe)

(declare-function blink-search-render "blink-search-render")
(declare-function eaf-open-in-file-manager "eaf-file-manager" (path))

(defun blink-search-get-theme-mode ()
  "Get theme mode, dark or light."
  (prin1-to-string (frame-parameter nil 'background-mode)))

(defun blink-search-color-blend (c1 c2 alpha)
  "Blend two colors C1 and C2 with ALPHA.
C1 and C2 are hexidecimal strings.
ALPHA is a number between 0.0 and 1.0 which corresponds to the
influence of C1 on the result."
  (apply (lambda (r g b)
           (format "#%02x%02x%02x"
                   (ash r -8)
                   (ash g -8)
                   (ash b -8)))
         (cl-mapcar
          (lambda (x y)
            (round (+ (* x alpha) (* y (- 1 alpha)))))
          (color-values c1) (color-values c2))))

(defun blink-search-init-colors (&optional force)
  "Derive the faces of blink-search from the current theme.

FORCE recomputes the colours even when they are already set, which is
what a theme change needs."
  ;; Avoid background around input string.
  (with-current-buffer blink-search-input-buffer
    (face-remap-add-relative 'hl-line :background (face-background 'default)))

  (let* ((is-dark-mode (string-equal (blink-search-get-theme-mode) "dark"))
         (blend-background (if is-dark-mode "#000000" "#AAAAAA"))
         (default-background (face-attribute 'default :background)))
    ;; Fallback to background of `default' face if `blink-search-color-blend' test failed.
    (unless (ignore-errors
              (blink-search-color-blend default-background blend-background 0.6))
      (setq default-background (if is-dark-mode "#000000" "#AAAAAA")))

    ;; Make sure menu follow the theme of Emacs.
    (when (or force (equal (face-attribute 'blink-search-select-face :background) 'unspecified))
      (set-face-background 'blink-search-select-face (blink-search-color-blend default-background blend-background 0.6)))
    (when (or force (equal (face-attribute 'blink-search-select-face :foreground) 'unspecified))
      (set-face-foreground 'blink-search-select-face (face-attribute 'font-lock-function-name-face :foreground)))))

(defun blink-search-reset-colors (&rest _args)
  "Recompute the blink-search colours and redraw the menu.

It is added as an advice of `load-theme', so it runs whenever the user
changes the theme."
  ;; Reset colors.
  (when (get-buffer blink-search-input-buffer)
    (blink-search-init-colors t)
    (blink-search-render)))

(if (daemonp)
    ;; The :background of 'default is unavailable until frame is created in
    ;; daemon mode.
    (add-hook 'server-after-make-frame-hook
              (lambda ()
                (advice-add #'load-theme :after #'blink-search-reset-colors)
                ;; Compensation for missing the first `load-thme' in
                ;; `after-init-hook'.
                (blink-search-reset-colors)))
  (advice-add #'load-theme :after #'blink-search-reset-colors))

(defun blink-search-get-window-allocation (&optional window)
  "Get WINDOW allocation."
  (let* ((window-edges (window-pixel-edges window))
         (x (nth 0 window-edges))
         (y (+ (nth 1 window-edges)
               (if (version< emacs-version "27.0")
                   (window-header-line-height window)
                 (window-tab-line-height window))))
         (w (- (nth 2 window-edges) x))
         (h (- (nth 3 window-edges) (window-mode-line-height window) y)))
    (list x y w h)))

(defun blink-search-disable-options (&optional disable-cursor)
  "Disable many options for blink-search buffers.

DISABLE-CURSOR also hides the cursor, which is what the tooltip and
candidate buffers want."
  ;; Disable line numbers mode.
  (when display-line-numbers
    (setq-local display-line-numbers nil))
  ;; Disable tab-line.
  (when (version< "27.0" emacs-version)
    (setq-local tab-line-format nil))
  ;; Disable hl-line, header-line and mode-line in input buffer.
  (setq-local header-line-format nil)
  (setq-local mode-line-format nil)
  ;; Disable cursor type if option `disable-cursor' is non-nil.
  (when disable-cursor
    (setq-local cursor-type nil)))

(defun blink-search-select-window (window)
  "Select WINDOW when it is still live."
  (when (window-live-p window)
    (select-window window)))

(defun blink-search-show-backend-window ()
  "Show the backend buffer, splitting the window when it is not visible."
  (unless (get-buffer-window blink-search-backend-buffer)
    (save-excursion
      (if (and blink-search-enable-posframe blink-search-posframe-preview-window)
          (set-window-buffer blink-search-posframe-preview-window blink-search-backend-buffer)
        (blink-search-select-window (get-buffer-window blink-search-candidate-buffer))
        (split-window (selected-window) nil 'right t)
        (other-window 1))
      (switch-to-buffer blink-search-backend-buffer)

      (blink-search-select-window (get-buffer-window blink-search-input-buffer)))))

(defun blink-search-hide-backend-window ()
  "Hide the backend buffer again."
  (when (get-buffer-window blink-search-backend-buffer)
    (save-excursion
      (unless blink-search-enable-posframe
        (delete-window (get-buffer-window blink-search-backend-buffer)))

      (blink-search-select-window (get-buffer-window blink-search-input-buffer)))))

(defun blink-search-bind-quit-keys (buffer)
  "Make `C-g' leave the search from BUFFER too.

The menu keeps the cursor in the input buffer, but a preview can leave the
focus in another pane, and `C-g' there ran `keyboard-quit', which only beeps
while the popup stayed on screen."
  (with-current-buffer buffer
    (local-set-key (kbd "C-g") #'blink-search-quit)
    (local-set-key (kbd "ESC ESC ESC") #'blink-search-quit)))

(defun blink-search-posframe-parent-frame ()
  "Return a live frame that is not blink-search's own posframe.

`posframe-show' makes the popup a child of the selected frame, and it
refuses a frame that is its own parent with \"Circular specification of
`parent-frame'\".  That happens when the posframe of an earlier session is
still selected: it is hidden rather than killed, so the next visit finds it
as the selected frame and hands it to `posframe-show' as the parent of
itself.  The frame the menu was started from is the right parent, and any
real frame is better than the posframe."
  (let ((posframe blink-search-posframe-frame))
    (or (and (frame-live-p blink-search-posframe-emacs-frame)
             (not (eq blink-search-posframe-emacs-frame posframe))
             blink-search-posframe-emacs-frame)
        (and (frame-live-p (selected-frame))
             (not (eq (selected-frame) posframe))
             (selected-frame))
        (seq-find (lambda (frame)
                    (and (frame-live-p frame) (not (eq frame posframe))))
                  (frame-list))
        (selected-frame))))

(defun blink-search-posframe-show (buffer &optional parent)
  "Show BUFFER in a posframe that is sized by the posframe options.

PARENT is the frame the popup hangs from; it must not be the popup itself,
so it is passed explicitly rather than left to `posframe-show' and the
selected frame."
  (let* ((posframe-height (round (* (frame-height) blink-search-posframe-height-ratio)))
         (posframe-width (round (* (frame-width) blink-search-posframe-width-ratio))))
    (apply #'posframe-show
           (get-buffer buffer)
           :poshandler #'posframe-poshandler-frame-center
           (append
            (list :parent-frame (or parent (blink-search-posframe-parent-frame)))
            (list
             :max-height posframe-height
             :min-height posframe-height
             :min-width  posframe-width
             :max-width  posframe-width
             :border-width 2
             :border-color "gray"
             :accept-focus (equal buffer blink-search-input-buffer)
             )))))

(defun blink-search-init-bottom-layout ()
  "Lay the four blink-search buffers out in the selected window."
  ;; Clean layout.
  ;; NOTE: `ignore-errors' make sure start always successfully,
  ;; even no buffer does exist when Emacs first start.
  (ignore-errors
    (delete-other-windows)
    (split-window)
    (other-window 1))

  ;; Show input buffer.
  (switch-to-buffer blink-search-input-buffer)

  ;; Show tooltip buffer.
  (split-window (selected-window) (line-pixel-height) 'below t)
  (split-window (selected-window) nil 'right t)
  (other-window 1)
  (switch-to-buffer blink-search-tooltip-buffer)

  ;; Show candidate buffer.
  (other-window 1)
  (switch-to-buffer blink-search-candidate-buffer)

  ;; Show backend buffer.
  (split-window (selected-window) nil 'right t)
  (other-window 1)
  (switch-to-buffer blink-search-backend-buffer)

  ;; Select input window.
  (blink-search-select-window (get-buffer-window blink-search-input-buffer)))

(defun blink-search-init-popup-layout ()
  "Lay the four blink-search buffers out inside a posframe popup."
  ;; Choose the frame to hang the popup from before creating it, and go back
  ;; to it when a posframe of an earlier session is what is selected right
  ;; now.  Otherwise the popup would be told to become its own child.
  (let ((parent (blink-search-posframe-parent-frame)))
    (setq blink-search-posframe-emacs-frame parent)
    (when (and (frame-live-p blink-search-posframe-frame)
               (eq (selected-frame) blink-search-posframe-frame))
      (make-frame-invisible blink-search-posframe-frame)
      (select-frame-set-input-focus parent))
    (setq blink-search-posframe-frame
          (blink-search-posframe-show blink-search-input-buffer parent)))

  (when blink-search-posframe-standalone
    (set-frame-parameter blink-search-posframe-frame 'parent-frame nil))

  ;; Make popup frame's font same as Emacs frame one.
  (with-selected-frame blink-search-posframe-frame
    (set-frame-font (with-selected-frame blink-search-posframe-emacs-frame
                      (face-attribute 'default :font))))

  (select-frame-set-input-focus blink-search-posframe-frame)

  (when (equal (length (window-list)) 1)
    (split-window (selected-window) (line-pixel-height) 'below t)
    (split-window (selected-window) nil 'right t)

    (dolist (buffer (list blink-search-tooltip-buffer
                          blink-search-candidate-buffer
                          blink-search-backend-buffer))
      (when (equal buffer blink-search-backend-buffer)
        (split-window (selected-window) nil 'right t))
      (other-window 1)
      (switch-to-buffer buffer)
      (when (equal buffer blink-search-backend-buffer)
        (setq blink-search-posframe-preview-window (selected-window)))))

  (blink-search-select-window (get-buffer-window blink-search-input-buffer))
  (setq-local cursor-type 'box)
  (set-window-margins (get-buffer-window blink-search-input-buffer) 1 1))

(defun blink-search-preview-select-window ()
  "Select the window that previews the candidate selected right now."
  (if blink-search-enable-posframe
      (unless (blink-search-select-window blink-search-posframe-preview-window)
        (blink-search-select-window (get-buffer-window blink-search-candidate-buffer))
        (split-window (selected-window) nil 'right t)
        (other-window 1)
        (setq blink-search-posframe-preview-window (selected-window)))
    (other-window -1)))

(cl-defmacro blink-search-select-input-window (&rest body)
  "Run BODY from the preview window, then return to the input window.

The input window is the only window blink-search keeps the cursor in,
so every action that visits another buffer has to come back to it."
  `(let* ((inhibit-message t)
          (input-window (get-buffer-window blink-search-input-buffer)))
     (when input-window
       (select-window input-window)
       (blink-search-preview-select-window)

       ,@body

       (select-window input-window)
       )))

(defun blink-search-select-start-buffer (buffer)
  "Switch to BUFFER, the buffer the search was started from.

The switch happens from the preview window, so that the popup layout
does not lose its input window."
  (unless blink-search-enable-posframe
    (blink-search-select-input-window
     (switch-to-buffer buffer))))

(defun blink-search-open-file (candidate)
  "Open CANDIDATE as a file or a directory.

A directory is handed to `blink-search-file-manager'; a file is opened
by `find-file'."
  (cond ((and (eq blink-search-file-manager 'eaf-file-manager)
              (file-directory-p candidate)
              (featurep 'eaf-file-manager))
         (eaf-open-in-file-manager candidate))
        ((and (eq blink-search-file-manager 'dired)
              (file-directory-p candidate))
         (dired candidate))
        (t (find-file candidate))))

(defun blink-search-continue-search (path)
  "Search again, restricted to the directory PATH.

The Python half calls this when the user continues the search from a
candidate that is a directory."
  (if (file-directory-p path)
      (progn
        (setq blink-search-continue-directory path)
        (with-current-buffer blink-search-input-buffer
          (erase-buffer))
        (message "[blink-search] continue search at: %s" path))
    (message "[blink-search] '%s' is not directory, can't continue search." path)))

(provide 'blink-search-ui)

;;; blink-search-ui.el ends here
