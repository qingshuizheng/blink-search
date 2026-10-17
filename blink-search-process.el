;;; blink-search-process.el --- The Python process of blink-search  -*- lexical-binding: t; -*-

;; Filename: blink-search-process.el
;; Description: The Python process of blink-search
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
;; Everything that touches the Python search process: the EPC server Emacs
;; listens on, the EPC manager that talks back to it, the process lifecycle,
;; and the callbacks the Python half calls into Emacs through.
;;
;; The names of those callbacks are the protocol, and they are listed in
;; blink-search-protocol.el; this file is where they are implemented.  The
;; asynchronous entry point is `blink-search-call-async', which sends one
;; request without blocking Emacs.

;;; Code:

(require 'blink-search-state)
(require 'blink-search-protocol)
(require 'blink-search-epc)

;; The backends are loaded after this file, and only the two that keep a timer
;; register a stop function.  Declaring them here keeps the process module
;; from having to load every backend eagerly.
(declare-function blink-search-stop-elisp-symbol-update "blink-search-elisp-symbol" ())
(declare-function blink-search-stop-recent-file-update "blink-search-recent-file" ())

(defun blink-search--start-epc-server ()
  "Start the EPC server Emacs listens on and return it.

The server is started once; a second call returns the running one.  The
EPC methods the Python process may call are registered here, and the
port is stored in `blink-search-server-port'."
  (unless (process-live-p blink-search-server)
    (setq blink-search-server
          (blink-search-epc-server-start
           (lambda (mngr)
             (let ((mngr mngr))
               (blink-search-epc-define-method mngr 'eval-in-emacs 'blink-search--eval-in-emacs-func)
               (blink-search-epc-define-method mngr 'get-emacs-var 'blink-search--get-emacs-var-func)
               (blink-search-epc-define-method mngr 'get-emacs-vars 'blink-search--get-emacs-vars-func)
               ))))
    (if blink-search-server
        (setq blink-search-server-port (process-contact blink-search-server :service))
      (error "[Blink-Search] blink-search-server failed to start")))
  blink-search-server)

(defun blink-search--eval-in-emacs-func (sexp-string)
  "Evaluate the printed Elisp form SEXP-STRING.

This is the single entry point the Python half uses for every callback
it wants to run, including `message', `kill-new' and the commands of
the Elisp backends.  Return nil, because the EPC protocol rejects a
reply with more than one value."
  (eval (read sexp-string))
  ;; Return nil to avoid epc error `Got too many arguments in the reply'.
  nil)

(defun blink-search--get-emacs-var-func (var-name)
  "Return the value of the Emacs variable named VAR-NAME.

The result is a list of the value and of whether the value is a
boolean, printed as a string: python-epc turns a nil into an empty
list, so the flag is what lets the Python half tell nil from t."
  (let* ((var-symbol (intern var-name))
         (symbol-is-exist-p (boundp var-symbol))
         (var-value (if symbol-is-exist-p (symbol-value var-symbol) ""))
         ;; We need convert result of booleanp to string.
         ;; Otherwise, python-epc will convert all `nil' to [] at Python side.
         (var-is-bool (if symbol-is-exist-p (prin1-to-string (booleanp var-value)) "nil")))
    (list var-value var-is-bool)))

(defun blink-search--get-emacs-vars-func (&rest vars)
  "Return `blink-search--get-emacs-var-func' for each name in VARS."
  (mapcar #'blink-search--get-emacs-var-func vars))

(defun blink-search-call-async (method &rest args)
  "Call Python EPC function METHOD and ARGS asynchronously.

ARGS is passed as **one list**, not spread, and that is the whole
convention: `blink-search-epc-call-deferred' writes the wire form
`(call UID METHOD ARGS)', python-epc hands the element after the method name
to `func(*args)', and the element is this list.  Passing `(list args)'
instead would wrap it once more, so `search' received one positional
argument -- the argument list -- and answered that two required positional
arguments were missing."
  (when (blink-search-epc-live-p blink-search-epc-process)
    (blink-search-deferred-chain
     (blink-search-epc-call-deferred blink-search-epc-process (read method) args))))

(defun blink-search-open-browser (url)
  "Open URL in the browser `blink-search-browser-function' names.

The Python half calls this instead of calling
`blink-search-browser-function' directly: the option holds a function
name, and only the variable is customised, never a function cell, so a
direct call would keep using the value it had when the package was
loaded."
  (funcall blink-search-browser-function url))

(define-obsolete-function-alias
  'blink-search-browser-function #'blink-search-open-browser "0.2")

;;;###autoload
(defun blink-search-restart-process ()
  "Stop and restart Blink-Search process."
  (interactive)
  (setq blink-search-is-starting nil)

  (blink-search-kill-process)
  (blink-search-start-process)
  (message "[Blink-Search] Process restarted."))

(defun blink-search-start-process ()
  "Start Blink-Search process if it isn't started."
  (setq blink-search-is-starting t)
  (unless (blink-search-epc-live-p blink-search-epc-process)
    ;; start epc server and set `blink-search-server-port'
    (blink-search--start-epc-server)
    (let* ((blink-search-args (append
                               (list blink-search-python-file)
                               (list (number-to-string blink-search-server-port))
                               )))

      ;; Set process arguments.
      (if blink-search-enable-debug
          (progn
            (setq blink-search-internal-process-prog "gdb")
            (setq blink-search-internal-process-args (append (list "-batch" "-ex" "run" "-ex" "bt" "--args" blink-search-python-command) blink-search-args)))
        (setq blink-search-internal-process-prog blink-search-python-command)
        (setq blink-search-internal-process-args blink-search-args))

      ;; Start python process.
      (let ((process-connection-type (not (blink-search--called-from-wsl-on-windows-p))))
        (setq blink-search-internal-process
              (apply 'start-process
                     blink-search-name blink-search-name
                     blink-search-internal-process-prog blink-search-internal-process-args)))
      (set-process-query-on-exit-flag blink-search-internal-process nil))))

(defun blink-search--called-from-wsl-on-windows-p ()
  "Check whether blink-search is called by Emacs on WSL and is running on Windows."
  (and (eq system-type 'gnu/linux)
       (string-match-p ".exe" blink-search-python-command)))

;;;###autoload
(defun blink-search-kill-process ()
  "Stop Blink-Search process and kill all Blink-Search buffers."
  (interactive)

  ;; Run stop process hooks.
  (run-hooks 'blink-search-stop-process-hook)

  ;; Kill process after kill buffer, make application can save session data.
  (blink-search--kill-python-process)

  ;; Only the two backends that keep an idle timer have a stop function, and
  ;; neither is loaded when Emacs exits before blink-search was used at all.
  (when (fboundp 'blink-search-stop-elisp-symbol-update)
    (blink-search-stop-elisp-symbol-update))
  (when (fboundp 'blink-search-stop-recent-file-update)
    (blink-search-stop-recent-file-update))
  )

(add-hook 'kill-emacs-hook #'blink-search-kill-process)

(defun blink-search--kill-python-process ()
  "Kill Blink-Search background python process."
  (when (blink-search-epc-live-p blink-search-epc-process)
    ;; Cleanup before exit Blink-Search server process.
    (blink-search-call-async "cleanup")
    ;; Delete Blink-Search server process.
    (blink-search-epc-stop-epc blink-search-epc-process)
    ;; Kill *blink-search* buffer.
    (when (get-buffer blink-search-name)
      (kill-buffer blink-search-name))
    (setq blink-search-epc-process nil)
    (message "[Blink-Search] Process terminated.")))

(defun blink-search--first-start (blink-search-epc-port)
  "Build the EPC layer from the port BLINK-SEARCH-EPC-PORT the server chose.

The Python process announces its port with `blink-search--first-start'
once its EPC server is up.  This sets up the manager Emacs talks to the
Python process through, clears `blink-search-is-starting', and runs the
start up lists so that every backend pushes its state to Python."
  ;; Make EPC process.
  (setq blink-search-epc-process (make-blink-search-epc-manager
                                  :server-process blink-search-internal-process
                                  :commands (cons blink-search-internal-process-prog blink-search-internal-process-args)
                                  :title (mapconcat 'identity (cons blink-search-internal-process-prog blink-search-internal-process-args) " ")
                                  :port blink-search-epc-port
                                  :connection (blink-search-epc-connect "127.0.0.1" blink-search-epc-port)
                                  ))
  (blink-search-epc-init-epc-layer blink-search-epc-process)
  (setq blink-search-is-starting nil)

  (dolist (update-func blink-search-idle-update-list)
    (funcall update-func))

  (dolist (update-func blink-search-start-update-list)
    (funcall update-func)))

(provide 'blink-search-process)

;;; blink-search-process.el ends here
