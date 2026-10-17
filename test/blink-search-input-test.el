;;; blink-search-input-test.el --- The prefix rule of the input buffer  -*- lexical-binding: t; -*-

;;; Commentary:
;; The input buffer is one line of text, and its first character decides which
;; backend answers: `#' the current buffer, `!' the directory, `;' the PDFs
;; and `:' one PDF.  That rule used to be a `cond' inside the
;; `after-change-functions' callback, where nothing could check it; it is a
;; table and a lookup now, and this is the check.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-input-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-input)

(ert-deftest blink-search-input-prefix-picks-the-backend ()
  "Every prefix of the table names the backend it stands for."
  (should (equal (blink-search-input-backend "#anything") "Current Buffer"))
  (should (equal (blink-search-input-backend "!anything") "Grep File"))
  (should (equal (blink-search-input-backend ";anything") "Grep PDF"))
  (should (equal (blink-search-input-backend ":anything") "PDF")))

(ert-deftest blink-search-input-full-width-prefixes-work-too ()
  "The full width forms are accepted, for a keyboard with an IME on."
  (should (equal (blink-search-input-backend "！anything") "Grep File"))
  (should (equal (blink-search-input-backend "；anything") "Grep PDF"))
  (should (equal (blink-search-input-backend "：anything") "PDF")))

(ert-deftest blink-search-input-a-plain-keyword-has-no-backend ()
  "A keyword without a prefix searches every backend."
  (should-not (blink-search-input-backend "blink"))
  (should-not (blink-search-input-backend ""))
  ;; a prefix that is not at the start of the keyword does not count
  (should-not (blink-search-input-backend "search #here")))

(ert-deftest blink-search-input-the-keyword-loses-its-prefix ()
  "The prefix is not part of the keyword the backends search for."
  (should (equal (blink-search-input-keyword "#defun") "defun"))
  (should (equal (blink-search-input-keyword "！notes") "notes"))
  (should (equal (blink-search-input-keyword "blink") "blink")))

(ert-deftest blink-search-input-a-lone-prefix-gives-an-empty-keyword ()
  "A prefix on its own searches its backend for nothing."
  (should (equal (blink-search-input-backend "#") "Current Buffer"))
  (should (equal (blink-search-input-keyword "#") "")))

(ert-deftest blink-search-input-every-prefix-names-a-known-backend ()
  "The table names backends, not free text.

The names are the ones the Python half knows; a typo here makes a prefix
silently search nothing at all."
  (dolist (entry blink-search-input-prefixes)
    (should (stringp (car entry)))
    (should (= (length (car entry)) 1))
    (should (member (cadr entry)
                    '("Current Buffer" "Grep File" "Grep PDF" "PDF")))))

(provide 'blink-search-input-test)
;;; blink-search-input-test.el ends here
