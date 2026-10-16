;;; blink-search-protocol-test.el --- The protocol as data  -*- lexical-binding: t; -*-

;;; Commentary:
;; The protocol tables in blink-search-protocol.el are the contract between
;; the two halves of the package.  The Elisp reader is what makes them
;; trustworthy -- a regular expression over the file could not follow the
;; nested lists a Lisp form is made of -- so the tests below read the tables
;; the same way scripts/check-protocol.py does.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L backend -L test -l test/blink-search-protocol-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-protocol)

(ert-deftest blink-search-protocol-version-is-a-number ()
  "The protocol version is a string that both halves can compare."
  (should (stringp blink-search-protocol-version))
  (should (string-match-p "\\`[0-9]+\\'" blink-search-protocol-version)))

(ert-deftest blink-search-protocol-tables-are-cons-cells ()
  "Every entry of the two tables is (NAME . DESCRIPTION)."
  (dolist (table (list blink-search-protocol-emacs-methods
                       blink-search-protocol-python-methods))
    (should (> (length table) 0))
    (dolist (entry table)
      (should (consp entry))
      (should (symbolp (car entry)))
      (should (stringp (cdr entry))))))

(ert-deftest blink-search-protocol-method-names-are-unique ()
  "No method is declared twice in one table."
  (dolist (table (list blink-search-protocol-emacs-methods
                       blink-search-protocol-python-methods))
    (let ((names (mapcar #'car table)))
      (should (equal names (delete-dups (copy-sequence names)))))))

(ert-deftest blink-search-protocol-lists-every-backend-update ()
  "The declared backend updates are named like the backends they feed.

This list is what the Elisp half and the Python half have to agree on: one
entry per module in backend/.  scripts/check-protocol.py is the gate that
compares it against the modules themselves; the test below only says the
shape of the list is right, so that a hand edit that drops an entry or
pastes a description into it is caught at once."
  (should (> (length blink-search-protocol-backend-update-methods) 0))
  (dolist (method blink-search-protocol-backend-update-methods)
    (should (symbolp method))
    (should (string-match-p "\\`search_[a-z0-9_]+_update\\'" (symbol-name method))))
  (let ((names (mapcar #'symbol-name blink-search-protocol-backend-update-methods)))
    (should (equal names (delete-dups (copy-sequence names))))))

(provide 'blink-search-protocol-test)
;;; blink-search-protocol-test.el ends here
