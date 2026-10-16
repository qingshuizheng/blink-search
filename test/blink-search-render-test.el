;;; blink-search-render-test.el --- The pure parts of the menu drawing  -*- lexical-binding: t; -*-

;;; Commentary:
;; The functions under test do not touch a window, a frame or the Python
;; process: they take a string and return a string.  That is on purpose --
;; they are the parts of the drawing code that can be checked in batch Emacs,
;; which is where the CI runs.
;;
;; Run with:
;;   Emacs -Q --batch -L . -L test -l test/blink-search-render-test.el \
;;         -f ert-run-tests-batch-and-exit

;;; Code:

(require 'ert)
(require 'blink-search-render)

(ert-deftest blink-search-render-candidate-shortens-a-long-path ()
  "A candidate longer than the menu keeps both of its ends."
  (let ((candidate "a/very/long/path/that/does/not/fit/in/the/menu/at/all.el"))
    (should (equal (blink-search-render-candidate "History" candidate 20)
                   "a/very/lon.../at/all.el"))))

(ert-deftest blink-search-render-candidate-keeps-a-short-one ()
  "A candidate that fits is returned unchanged."
  (should (equal (blink-search-render-candidate "History" "short.el" 20) "short.el")))

(ert-deftest blink-search-render-candidate-recent-file-uses-the-base-name ()
  "A recent file is shown as its base name, however long the path is."
  (should (equal (blink-search-render-candidate "Recent File" "/tmp/a/b/c.el" 5) "c.el")))

(ert-deftest blink-search-render-candidate-grep-keeps-the-head ()
  "A line of a file is cut from the end, where the interesting part is not."
  (should (equal (blink-search-render-candidate
                  "Grep File" "file.el:12:3: (message \"a long line of code\")" 20)
                 "file.el:12:3: (me...")))

(ert-deftest blink-search-get-candidate-text-strips-carriage-returns ()
  "A candidate that came from a file with CRLF endings loses its CR.

The newline at the end of the line is kept: the caller is a menu that
inserts the text into a buffer, and the row ends there anyway."
  (should (equal (blink-search-get-candidate-text "line\r\r\n") "line\n"))
  (should (equal (blink-search-get-candidate-text '(:text "line\r")) "line")))

(ert-deftest blink-search-get-candidate-matches-returns-the-offsets ()
  "The match offsets of a structured candidate are returned as they are."
  (should (equal (blink-search-get-candidate-matches '(:text "abc" :matches ((1 2)))) '((1 2))))
  (should (equal (blink-search-get-candidate-matches "plain string") nil)))

(ert-deftest blink-search-column-to-string-index-counts-characters ()
  "A byte column is turned into the character index that starts it."
  (should (= (blink-search-column-to-string-index "abc" 1) 1))
  (should (= (blink-search-column-to-string-index "abc" 3) 3))
  ;; one Chinese character is three bytes, so byte 3 is character 1 and
  ;; byte 6 is after it and after the "a" that follows.
  (should (= (blink-search-column-to-string-index "中abc" 3) 1))
  (should (= (blink-search-column-to-string-index "中abc" 6) 4)))

(provide 'blink-search-render-test)
;;; blink-search-render-test.el ends here
