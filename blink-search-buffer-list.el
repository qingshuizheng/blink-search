;;; blink-search-buffer-list.el --- Buffer list backend for blink-search   -*- lexical-binding: t; -*-

;; Filename: blink-search-buffer-list.el
;; Description: Buffer list backend for blink-search
;; Author: Andy Stewart <lazycat.manatee@gmail.com>
;; Maintainer: Andy Stewart <lazycat.manatee@gmail.com>
;; Copyright (C) 2022, Andy Stewart, all rights reserved.
;; Created: 2022-11-04 08:52:38
;; Version: 0.1
;; Last-Updated: 2022-11-04 08:52:38
;;           By: Andy Stewart
;; URL: https://www.github.org/manateelazycat/blink-search-buffer-list
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
;; Buffer list backend for blink-search: it pushes the names of the open
;; buffers to the Python half, which then matches them against the keyword.
;;
;; When sort-tab is installed the names are pushed in the order sort-tab shows
;; the tabs in, so that a candidate list of buffers reads the same way as the
;; tab bar does.

;;; Require
(require 'blink-search-state)
(require 'blink-search-process)

;;; Code:

(defvar sort-tab-visible-buffers)

(defun blink-search-buffer-list-update ()
  "Push the names of the open buffers to the Python half.
With sort-tab installed the tab order is preserved, so that the
candidate list reads the same way as the tab bar."
  (when (blink-search-epc-live-p blink-search-epc-process)
    (if (featurep 'sort-tab)
        (blink-search-call-async "search_sort_buffer_list_update" (mapcar #'buffer-name (append sort-tab-visible-buffers (buffer-list))))
      (blink-search-call-async "search_buffer_list_update" (mapcar #'buffer-name (buffer-list))))))

(add-to-list 'blink-search-start-update-list #'blink-search-buffer-list-update t)

(provide 'blink-search-buffer-list)
;;; blink-search-buffer-list.el ends here
