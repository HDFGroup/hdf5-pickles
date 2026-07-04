;;; hdf5-poke-core.el --- Core state and GNU poke protocol -*- lexical-binding: t; -*-

;; Copyright (C) 2026 The HDF Group.

;; Author: HDF Group
;; Keywords: data, files, tools
;; SPDX-License-Identifier: GPL-3.0-or-later

;;; Commentary:

;; Foundational layer for hdf5-poke: customization, buffer-local state, the GNU
;; poke process and protocol, and pure data/path helpers.  The inspector UI --
;; major modes, renderers, the path tree, and commands -- lives in
;; `hdf5-poke-ui'.

;;; Code:

(require 'cl-lib)
(require 'comint)
(require 'subr-x)

(defgroup hdf5-poke nil
  "Inspect and edit HDF5 files through GNU poke pickles."
  :group 'data
  :prefix "hdf5-poke-")

(defconst hdf5-poke--source-directory
  (file-name-directory (or load-file-name buffer-file-name default-directory)))

(defconst hdf5-poke--repository-directory
  (file-name-directory
   (directory-file-name hdf5-poke--source-directory)))

(defcustom hdf5-poke-program "poke"
  "GNU poke executable used by `hdf5-poke-open-file'."
  :type 'string)

(defcustom hdf5-poke-pickles-directory
  (expand-file-name "pickles" hdf5-poke--repository-directory)
  "Directory containing the HDF5 pickle files."
  :type 'directory)

(defcustom hdf5-poke-load-modules
  '("hdf5_poke_emacs")
  "Pickle modules loaded when a new poke session starts.

The command layer from `h5explain/pickles/h5explain.pk' is deliberately not loaded."
  :type '(repeat string))

(defcustom hdf5-poke-no-init-file t
  "When non-nil, start GNU poke with -q to avoid user init-file effects."
  :type 'boolean)

(defcustom hdf5-poke-default-superblock-offset "0#B"
  "Default HDF5 superblock offset used by new sessions.

Most HDF5 files start at byte 0.  Files with a user block may need an offset
such as 512#B."
  :type 'string)

(defcustom hdf5-poke-show-process-buffer nil
  "When non-nil, display the GNU poke process buffer after sending commands."
  :type 'boolean)

(defcustom hdf5-poke-enable-writes nil
  "When non-nil, allow `hdf5-poke-write-expression' to send write expressions.

HDF5 metadata writes are low-level byte edits.  Many useful edits also require
dependent metadata updates, such as checksums."
  :type 'boolean)

(defcustom hdf5-poke-prompt-regexp "^(poke) "
  "Prompt regexp used in the GNU poke comint buffer."
  :type 'regexp)

(defcustom hdf5-poke-preview-max-bytes 256
  "Maximum dataset payload bytes requested by preview commands."
  :type 'natnum)

(defcustom hdf5-poke-request-timeout 15
  "Seconds to wait for a GNU poke protocol response before failing a request.

A value of 0 disables the timeout.  Timed-out requests are reported in the echo
area and the session command log; a late response that arrives afterwards is
ignored safely."
  :type 'number)

(defvar hdf5-poke--last-session-buffer nil)
(defvar hdf5-poke--command-counter 0)

(defvar-local hdf5-poke--target-file nil)
(defvar-local hdf5-poke--process-buffer nil)
(defvar-local hdf5-poke--inspector-buffer nil)
(defvar-local hdf5-poke--superblock-offset nil)
(defvar-local hdf5-poke--origin-session nil)
(defvar-local hdf5-poke--object-header-offset nil)
(defvar-local hdf5-poke--object-path nil)
(defvar-local hdf5-poke--path-stack nil)
(defvar-local hdf5-poke--object-kind-cache nil)
(defvar-local hdf5-poke--path-cache nil)
(defvar-local hdf5-poke--chunk-index-offset nil)
(defvar-local hdf5-poke--chunk-index-ndims nil)
(defvar-local hdf5-poke--chunk-index-dims nil)
(defvar-local hdf5-poke--chunk-index-record nil)
(defvar-local hdf5-poke--tree-root nil)
(defvar-local hdf5-poke--pending-requests nil)
(defvar-local hdf5-poke--protocol-fragment "")
(defvar-local hdf5-poke--protocol-current-id nil)
(defvar-local hdf5-poke--protocol-payload nil)
(defvar-local hdf5-poke--protocol-raw-lines nil)
(defvar-local hdf5-poke--protocol-in-raw nil)

(define-derived-mode hdf5-poke-process-mode comint-mode "HDF5-Poke-Process"
  "Comint mode for a GNU poke process managed by hdf5-poke."
  (setq-local comint-prompt-regexp hdf5-poke-prompt-regexp)
  (setq-local comint-use-prompt-regexp t)
  (setq-local hdf5-poke--pending-requests
              (or hdf5-poke--pending-requests
                  (make-hash-table :test 'eql)))
  (setq-local hdf5-poke--protocol-fragment "")
  (setq-local hdf5-poke--protocol-current-id nil)
  (setq-local hdf5-poke--protocol-payload nil)
  (setq-local hdf5-poke--protocol-raw-lines nil)
  (setq-local hdf5-poke--protocol-in-raw nil)
  (add-hook 'comint-output-filter-functions
            #'hdf5-poke--comint-output-filter nil t))

(defun hdf5-poke--environment ()
  "Return a process environment with the pickles on POKE_LOAD_PATH."
  (let* ((pickles (file-truename hdf5-poke-pickles-directory))
         (existing (getenv "POKE_LOAD_PATH"))
         (load-path (string-join
                     (delq nil (list pickles
                                      (and existing
                                           (not (string-empty-p existing))
                                           existing)))
                     path-separator)))
    (cons (concat "POKE_LOAD_PATH=" load-path) process-environment)))

(defun hdf5-poke--bootstrap-source ()
  "Return poke source used to initialize a session."
  (string-join
   (append
    '(".set pretty-print yes"
      ".set omode tree")
    (mapcar (lambda (module) (format "load %s" module))
            hdf5-poke-load-modules))
   "\n"))

(defun hdf5-poke--session-buffer ()
  "Return the current inspector session buffer."
  (cond
   ((derived-mode-p 'hdf5-poke-mode)
    (current-buffer))
   ((and (local-variable-p 'hdf5-poke--origin-session)
         (buffer-live-p hdf5-poke--origin-session))
    hdf5-poke--origin-session)
   ((and (local-variable-p 'hdf5-poke--inspector-buffer)
         (buffer-live-p hdf5-poke--inspector-buffer))
    hdf5-poke--inspector-buffer)
   ((buffer-live-p hdf5-poke--last-session-buffer)
    hdf5-poke--last-session-buffer)
   (t
    (user-error "No hdf5-poke session; run M-x hdf5-poke-open-file"))))

(defun hdf5-poke--process (&optional session-buffer)
  "Return the GNU poke process for SESSION-BUFFER."
  (let* ((session-buffer (or session-buffer (hdf5-poke--session-buffer)))
         (process-buffer (buffer-local-value 'hdf5-poke--process-buffer
                                             session-buffer))
         (process (and (buffer-live-p process-buffer)
                       (get-buffer-process process-buffer))))
    (unless (process-live-p process)
      (user-error "No live GNU poke process for this hdf5-poke session"))
    process))

(defun hdf5-poke--append-command (session-buffer title source)
  "Append TITLE and SOURCE to SESSION-BUFFER."
  (with-current-buffer session-buffer
    (let ((inhibit-read-only t))
      (goto-char (point-max))
      (unless (bolp) (insert "\n"))
      (insert "\n" title "\n"
              (make-string (length title) ?-) "\n"
              source "\n"))))

(defun hdf5-poke--send (title source)
  "Send SOURCE to the current poke process and record TITLE."
  (let* ((session-buffer (hdf5-poke--session-buffer))
         (process (hdf5-poke--process session-buffer))
         (process-buffer (process-buffer process)))
    (hdf5-poke--append-command session-buffer title source)
    (comint-send-string process source)
    (unless (string-suffix-p "\n" source)
      (comint-send-string process "\n"))
    (when hdf5-poke-show-process-buffer
      (display-buffer process-buffer))))

(defun hdf5-poke--offset-expression (offset)
  "Return a poke byte-offset expression for numeric OFFSET."
  (format "%d#B" offset))

(defun hdf5-poke--superblock-offset-expression ()
  "Return the current session's superblock byte-offset expression."
  (buffer-local-value 'hdf5-poke--superblock-offset
                      (hdf5-poke--session-buffer)))

(defun hdf5-poke--join-args (&rest args)
  "Join non-nil ARGS into a comma-separated GNU poke argument string."
  (string-join (delq nil args) ", "))

(defun hdf5-poke--request-args (offset &rest middle)
  "Return poke call arguments for byte OFFSET, MIDDLE, and the superblock offset.

Most protocol functions take a target byte offset, any extra MIDDLE arguments,
and the session superblock offset as their final argument."
  (apply #'hdf5-poke--join-args
         (hdf5-poke--offset-expression offset)
         (append middle (list (hdf5-poke--superblock-offset-expression)))))

(defun hdf5-poke--poke-string (value)
  "Return VALUE as a simple GNU poke string literal."
  (prin1-to-string value))

(defun hdf5-poke--fail-request (id request reason)
  "Report failed protocol request ID, described by REQUEST, because of REASON."
  (let ((timer (plist-get request :timer))
        (session (plist-get request :session))
        (text (format "hdf5-poke: %s request (id %d) failed: %s"
                      (or (plist-get request :title) "unknown")
                      id reason)))
    (when (timerp timer)
      (cancel-timer timer))
    (when (buffer-live-p session)
      (hdf5-poke--append-command session "Request failed" text))
    (message "%s" text)))

(defun hdf5-poke--flush-pending-requests (reason)
  "Fail every pending request in the current process buffer because of REASON."
  (when hdf5-poke--pending-requests
    (let (entries)
      (maphash (lambda (id request) (push (cons id request) entries))
               hdf5-poke--pending-requests)
      (clrhash hdf5-poke--pending-requests)
      (dolist (entry entries)
        (hdf5-poke--fail-request (car entry) (cdr entry) reason)))))

(defun hdf5-poke--request-timeout (process-buffer id)
  "Fail pending request ID in PROCESS-BUFFER when no response has arrived."
  (when (buffer-live-p process-buffer)
    (with-current-buffer process-buffer
      (when-let ((request (and hdf5-poke--pending-requests
                               (gethash id hdf5-poke--pending-requests))))
        (remhash id hdf5-poke--pending-requests)
        (hdf5-poke--fail-request
         id request
         (format "no response within %s s" hdf5-poke-request-timeout))))))

(defun hdf5-poke--process-sentinel (process _event)
  "Fail pending hdf5-poke requests when PROCESS is no longer live."
  (unless (process-live-p process)
    (let ((process-buffer (process-buffer process)))
      (when (buffer-live-p process-buffer)
        (with-current-buffer process-buffer
          (hdf5-poke--flush-pending-requests
           (format "GNU poke process %s" (process-status process))))))))

(defun hdf5-poke--send-request (title function args callback)
  "Send a protocol request for FUNCTION with ARGS and CALLBACK.

CALLBACK is called in the inspector session buffer with three arguments:
parsed records, raw text blocks, and parser errors.  If GNU poke does not
respond within `hdf5-poke-request-timeout' seconds, or the process dies first,
the request is failed instead of leaking."
  (let* ((session-buffer (hdf5-poke--session-buffer))
         (process (hdf5-poke--process session-buffer))
         (process-buffer (process-buffer process))
         (id (cl-incf hdf5-poke--command-counter))
         (source (format "%s(%d%s%s)"
                         function
                         id
                         (if (string-empty-p args) "" ", ")
                         args)))
    (with-current-buffer process-buffer
      (unless hdf5-poke--pending-requests
        (setq-local hdf5-poke--pending-requests
                    (make-hash-table :test 'eql)))
      (let ((timer (and (> hdf5-poke-request-timeout 0)
                        (run-at-time hdf5-poke-request-timeout nil
                                     #'hdf5-poke--request-timeout
                                     process-buffer id))))
        (puthash id
                 (list :callback callback
                       :session session-buffer
                       :title title
                       :timer timer)
                 hdf5-poke--pending-requests)))
    (hdf5-poke--append-command session-buffer title source)
    (comint-send-string process source)
    (comint-send-string process "\n")
    id))

(defun hdf5-poke--comint-output-filter (text)
  "Collect protocol records from GNU poke process output TEXT."
  (let* ((combined (concat hdf5-poke--protocol-fragment text))
         (parts (split-string combined "\n"))
         (ends-with-newline (string-suffix-p "\n" combined)))
    ;; `split-string' leaves an empty final part after a trailing newline;
    ;; without one, the final part is an incomplete line we carry over to the
    ;; next filter call.  Either way `butlast' yields the complete lines.
    (setq hdf5-poke--protocol-fragment
          (if ends-with-newline "" (car (last parts))))
    (dolist (line (butlast parts))
      (hdf5-poke--protocol-handle-line line))))

(defun hdf5-poke--protocol-handle-line (line)
  "Handle one complete protocol output LINE."
  (setq line (replace-regexp-in-string "\r\\'" "" line))
  (cond
   ((string-match "@@HDF5-POKE-BEGIN \\([0-9]+\\)" line)
    (setq hdf5-poke--protocol-current-id
          (string-to-number (match-string 1 line))
          hdf5-poke--protocol-payload nil
          hdf5-poke--protocol-raw-lines nil
          hdf5-poke--protocol-in-raw nil))
   ((string-match "@@HDF5-POKE-RAW-BEGIN \\([0-9]+\\)" line)
    (when (equal hdf5-poke--protocol-current-id
                 (string-to-number (match-string 1 line)))
      (setq hdf5-poke--protocol-in-raw t
            hdf5-poke--protocol-raw-lines nil)))
   ((string-match "@@HDF5-POKE-RAW-END \\([0-9]+\\)" line)
    (when (equal hdf5-poke--protocol-current-id
                 (string-to-number (match-string 1 line)))
      (push (cons :raw
                  (string-join (nreverse hdf5-poke--protocol-raw-lines)
                               "\n"))
            hdf5-poke--protocol-payload)
      (setq hdf5-poke--protocol-in-raw nil
            hdf5-poke--protocol-raw-lines nil)))
   ((string-match "@@HDF5-POKE-END \\([0-9]+\\)" line)
    (hdf5-poke--protocol-finish (string-to-number (match-string 1 line))))
   ((and hdf5-poke--protocol-current-id hdf5-poke--protocol-in-raw)
    (push (replace-regexp-in-string "^(poke) " "" line)
          hdf5-poke--protocol-raw-lines))
   (hdf5-poke--protocol-current-id
    (when (string-match "(\\(:record\\|:error\\)\\_>" line)
      (push (substring line (match-beginning 0))
            hdf5-poke--protocol-payload)))))

(defun hdf5-poke--protocol-finish (id)
  "Finish protocol request ID and dispatch its callback."
  (when (equal hdf5-poke--protocol-current-id id)
    (let ((payload (nreverse hdf5-poke--protocol-payload))
          records raws errors request callback session)
      (dolist (item payload)
        (if (and (consp item) (eq (car item) :raw))
            (push (cdr item) raws)
          (condition-case err
              (push (car (read-from-string item)) records)
            (error
             (push (format "%s while reading %S" err item) errors)))))
      (setq records (nreverse records)
            raws (nreverse raws)
            errors (nreverse errors)
            request (and hdf5-poke--pending-requests
                         (gethash id hdf5-poke--pending-requests)))
      (when request
        (remhash id hdf5-poke--pending-requests)
        (when-let ((timer (plist-get request :timer)))
          (cancel-timer timer))
        (setq callback (plist-get request :callback)
              session (plist-get request :session))
        (when (and callback (buffer-live-p session))
          (with-current-buffer session
            (funcall callback records raws errors)))))
    (setq hdf5-poke--protocol-current-id nil
          hdf5-poke--protocol-payload nil
          hdf5-poke--protocol-raw-lines nil
          hdf5-poke--protocol-in-raw nil)))

(defun hdf5-poke--read-offset (prompt)
  "Read and validate an HDF5 byte offset with PROMPT."
  (let ((text (string-trim (read-string prompt))))
    (unless (string-match-p "\\`\\(?:[0-9]+\\|0[xX][[:xdigit:]]+\\)\\'" text)
      (user-error "Offset must be decimal or hexadecimal, e.g. 48 or 0x30"))
    (concat text "#B")))

(defun hdf5-poke--read-offset-number (prompt)
  "Read an HDF5 byte offset with PROMPT and return it as a number."
  (let ((text (string-trim (read-string prompt))))
    (unless (string-match-p "\\`\\(?:[0-9]+\\|0[xX][[:xdigit:]]+\\)\\'" text)
      (user-error "Offset must be decimal or hexadecimal, e.g. 48 or 0x30"))
    (if (string-prefix-p "0x" (downcase text))
        (string-to-number (substring text 2) 16)
      (string-to-number text 10))))

(defun hdf5-poke--record (records type)
  "Return the first record in RECORDS whose `:record' is TYPE."
  (cl-find-if (lambda (record) (eq (plist-get record :record) type))
              records))

(defun hdf5-poke--records (records type)
  "Return all records in RECORDS whose `:record' is TYPE."
  (cl-remove-if-not (lambda (record) (eq (plist-get record :record) type))
                    records))

(defun hdf5-poke--field (record field)
  "Return FIELD from RECORD, displaying nil as an empty string."
  (let ((value (plist-get record field)))
    (cond
     ((null value) "")
     ((stringp value) value)
     (t (format "%s" value)))))

(defun hdf5-poke--session-cache (variable)
  "Return hash-table stored in session-local VARIABLE."
  (let ((session (hdf5-poke--session-buffer)))
    (or (buffer-local-value variable session)
        (with-current-buffer session
          (set variable (make-hash-table :test 'equal))))))

(defun hdf5-poke--object-kind-cache ()
  "Return the current session's object-kind cache."
  (hdf5-poke--session-cache 'hdf5-poke--object-kind-cache))

(defun hdf5-poke--path-cache ()
  "Return the current session's path cache."
  (hdf5-poke--session-cache 'hdf5-poke--path-cache))

(defun hdf5-poke--cached-object-kind (offset)
  "Return cached object kind for object-header OFFSET."
  (gethash offset (hdf5-poke--object-kind-cache)))

(defun hdf5-poke--remember-object-kind (offset kind)
  "Remember object-header OFFSET as KIND and return KIND."
  (when (and offset kind)
    (puthash offset kind (hdf5-poke--object-kind-cache)))
  kind)

(defun hdf5-poke--normalize-path (path)
  "Normalize absolute HDF5 PATH."
  (let ((path (string-trim (or path ""))))
    (when (string-empty-p path)
      (setq path "/"))
    (unless (string-prefix-p "/" path)
      (user-error "HDF5 paths must be absolute, e.g. /group/data"))
    (while (and (> (length path) 1)
                (string-suffix-p "/" path))
      (setq path (substring path 0 -1)))
    path))

(defun hdf5-poke--path-components (path)
  "Return normalized HDF5 PATH components."
  (let ((path (hdf5-poke--normalize-path path)))
    (if (string= path "/")
        nil
      (split-string (substring path 1) "/" t))))

(defun hdf5-poke--stack-path-for-offset (stack offset)
  "Return first path in STACK that points to OFFSET."
  (car (cl-find offset stack :key #'cdr :test #'equal)))

(defun hdf5-poke--stack-has-offset-p (stack offset)
  "Return non-nil when STACK already contains OFFSET."
  (and (hdf5-poke--stack-path-for-offset stack offset) t))

(defun hdf5-poke--records-object-kind (records)
  "Infer an object kind symbol from protocol RECORDS."
  (let ((messages (hdf5-poke--records records 'message)))
    (cond
     ((or (hdf5-poke--record records 'dataspace)
          (hdf5-poke--record records 'datatype)
          (hdf5-poke--record records 'layout)
          (cl-some (lambda (message)
                     (memq (plist-get message :type) '(1 3 8)))
                   messages))
      'dataset)
     ((or (hdf5-poke--record records 'link-storage)
          (cl-some (lambda (message)
                     (memq (plist-get message :type) '(2 6 10 17)))
                   messages))
      'group)
     (t 'unknown))))

(defun hdf5-poke--child-path (path name)
  "Return child path NAME under PATH."
  (let ((path (or path "/")))
    (if (string= path "/")
        (concat "/" name)
      (concat path "/" name))))

(defun hdf5-poke--path-label (path)
  "Return a compact display label for PATH."
  (if (or (null path) (string-empty-p path)) "/" path))

(defun hdf5-poke--path-stack-prefix (stack index)
  "Return STACK through INDEX inclusive."
  (cl-subseq stack 0 (1+ index)))

(provide 'hdf5-poke-core)

;;; hdf5-poke-core.el ends here
