;;; hdf5-poke-process-test.el --- Process smoke tests for hdf5-poke -*- lexical-binding: t; -*-

;; SPDX-License-Identifier: GPL-3.0-or-later

;;; Code:

(require 'ert)
(require 'cl-lib)

(defconst hdf5-poke-process-test--test-directory
  (file-name-directory (or load-file-name buffer-file-name)))

(defconst hdf5-poke-process-test--source-root
  (expand-file-name "../.." hdf5-poke-process-test--test-directory))

(load-file (expand-file-name "emacs/hdf5-poke.el"
                             hdf5-poke-process-test--source-root))

(defconst hdf5-poke-process-test--fixtures
  (file-name-as-directory
   (or (let ((fixtures (getenv "HDF5_POKE_TEST_FIXTURES")))
         (and fixtures
              (> (length fixtures) 0)
              (expand-file-name fixtures)))
       (expand-file-name "fixtures" hdf5-poke-process-test--test-directory))))

(defun hdf5-poke-process-test--fixture (name)
  "Return the absolute path to fixture NAME."
  (expand-file-name name hdf5-poke-process-test--fixtures))

(defun hdf5-poke-process-test--skip-unless-ready (&rest fixture-names)
  "Skip unless GNU poke and FIXTURE-NAMES are available."
  (unless (executable-find hdf5-poke-program)
    (ert-skip (format "Cannot find GNU poke executable: %s"
                      hdf5-poke-program)))
  (dolist (name fixture-names)
    (unless (file-exists-p (hdf5-poke-process-test--fixture name))
      (ert-skip (format "Missing fixture: %s" name)))))

(defun hdf5-poke-process-test--pending-count (session)
  "Return the pending protocol request count for SESSION."
  (let ((process-buffer (buffer-local-value 'hdf5-poke--process-buffer
                                            session)))
    (if (buffer-live-p process-buffer)
        (with-current-buffer process-buffer
          (if hdf5-poke--pending-requests
              (hash-table-count hdf5-poke--pending-requests)
            0))
      0)))

(defun hdf5-poke-process-test--wait (session &optional timeout)
  "Wait for SESSION protocol requests to finish."
  (let* ((process-buffer (buffer-local-value 'hdf5-poke--process-buffer
                                             session))
         (process (and (buffer-live-p process-buffer)
                       (get-buffer-process process-buffer)))
         (deadline (+ (float-time) (or timeout 5.0))))
    (while (and (process-live-p process)
                (> (hdf5-poke-process-test--pending-count session) 0)
                (< (float-time) deadline))
      (accept-process-output process 0.05))
    (when (> (hdf5-poke-process-test--pending-count session) 0)
      (ert-fail
       (format "Timed out waiting for hdf5-poke protocol requests in %s"
               (buffer-name session))))))

(defun hdf5-poke-process-test--cleanup ()
  "Kill hdf5-poke buffers and processes created by smoke tests."
  (dolist (buffer (buffer-list))
    (when (string-prefix-p "*hdf5-poke" (buffer-name buffer))
      (when-let ((process (get-buffer-process buffer)))
        (when (process-live-p process)
          (delete-process process)))
      (kill-buffer buffer))))

(defun hdf5-poke-process-test--with-session (fixture-name callback)
  "Open FIXTURE-NAME with hdf5-poke, run CALLBACK with the session buffer."
  (hdf5-poke-process-test--skip-unless-ready fixture-name)
  (let ((hdf5-poke-pickles-directory
         (expand-file-name "pickles" hdf5-poke-process-test--source-root))
        (file (hdf5-poke-process-test--fixture fixture-name)))
    (unwind-protect
        (let ((session (hdf5-poke-open-file file)))
          (hdf5-poke-process-test--wait session)
          (funcall callback session))
      (hdf5-poke-process-test--cleanup))))

(defun hdf5-poke-process-test--row-ids (buffer-name)
  "Return tabulated row ids from BUFFER-NAME."
  (with-current-buffer buffer-name
    (mapcar #'car tabulated-list-entries)))

(ert-deftest hdf5-poke-process-expands-dense-group-links ()
  (hdf5-poke-process-test--with-session
   "dense_group.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-links-at 195))
     (hdf5-poke-process-test--wait session)
     (let* ((rows (hdf5-poke-process-test--row-ids
                   "*hdf5-poke-links:dense_group.h5@195*"))
            (links (cl-remove-if-not
                    (lambda (row) (eq (plist-get row :record) 'link))
                    rows))
            (storage (cl-find-if
                      (lambda (row) (eq (plist-get row :record) 'link-storage))
                      rows)))
       (should (= 32 (length links)))
       (should (equal "dense" (plist-get storage :kind)))
       (should (equal "expanded" (plist-get storage :status)))
       (should (cl-find "dset_00" links
                        :key (lambda (row) (plist-get row :name))
                        :test #'equal))))))

(ert-deftest hdf5-poke-process-expands-old-style-group-links ()
  (hdf5-poke-process-test--with-session
   "old_style_group.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-links-at 800))
     (hdf5-poke-process-test--wait session)
     (let* ((rows (hdf5-poke-process-test--row-ids
                   "*hdf5-poke-links:old_style_group.h5@800*"))
            (links (cl-remove-if-not
                    (lambda (row) (eq (plist-get row :record) 'link))
                    rows))
            (storage (cl-find-if
                      (lambda (row) (eq (plist-get row :record) 'link-storage))
                      rows)))
       (should (= 32 (length links)))
       (should (equal "symbol-table" (plist-get storage :kind)))
       (should (equal "expanded" (plist-get storage :status)))
       (should (cl-find "dset_31" links
                        :key (lambda (row) (plist-get row :name))
                        :test #'equal))))))

(ert-deftest hdf5-poke-process-loads-tree-root-links ()
  (hdf5-poke-process-test--with-session
   "old_style_group.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-tree))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-tree:old_style_group.h5*"
       (should (derived-mode-p 'hdf5-poke-tree-mode))
       (should hdf5-poke--tree-root)
       (should (plist-get hdf5-poke--tree-root :loaded))
       (should (plist-get hdf5-poke--tree-root :expanded))
       (let ((group (cl-find "group"
                             (plist-get hdf5-poke--tree-root :children)
                             :key (lambda (node) (plist-get node :name))
                             :test #'equal)))
         (should group)
         (should (eq (plist-get group :kind) 'unknown)))
       (should (save-excursion
                 (goto-char (point-min))
                 (search-forward "group  @800" nil t)))
       (goto-char (point-min))
       (search-forward "group  @800")
       (hdf5-poke-tree-toggle))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-tree:old_style_group.h5*"
       (let ((group (cl-find "group"
                             (plist-get hdf5-poke--tree-root :children)
                             :key (lambda (node) (plist-get node :name))
                             :test #'equal)))
         (should (eq (plist-get group :kind) 'group))
         (should (plist-get group :loaded))
         (should (cl-find "dset_00"
                          (plist-get group :children)
                          :key (lambda (node) (plist-get node :name))
                          :test #'equal)))
       (goto-char (point-min))
       (search-forward "dset_00")
       (hdf5-poke-tree-toggle))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-tree:old_style_group.h5*"
       (let* ((group (cl-find "group"
                              (plist-get hdf5-poke--tree-root :children)
                              :key (lambda (node) (plist-get node :name))
                              :test #'equal))
              (dataset (cl-find "dset_00"
                                (plist-get group :children)
                                :key (lambda (node) (plist-get node :name))
                                :test #'equal)))
         (should (eq (plist-get dataset :kind) 'dataset))
         (should (plist-get dataset :loaded)))
       (should (save-excursion
                 (goto-char (point-min))
                 (search-forward "[dataset] dset_00" nil t)))))))

(defun hdf5-poke-process-test--assert-chunk-index
    (fixture-name offset ndims expected-kind expected-count
                  &optional expected-last-scaled-offsets expected-coord-ndims)
  "Assert chunk-index smoke behavior for FIXTURE-NAME."
  (hdf5-poke-process-test--with-session
   fixture-name
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-chunk-index-at offset ndims))
     (hdf5-poke-process-test--wait session)
     (let* ((buffer-name (format "*hdf5-poke-chunks:%s@%s*"
                                 fixture-name offset))
            (rows (hdf5-poke-process-test--row-ids buffer-name))
            (chunks (cl-remove-if-not
                     (lambda (row) (eq (plist-get row :record) 'chunk))
                     rows)))
       (with-current-buffer buffer-name
         (should (equal expected-kind
                        (plist-get hdf5-poke--chunk-index-record :kind)))
         (when expected-coord-ndims
           (should (= expected-coord-ndims
                      (plist-get hdf5-poke--chunk-index-record
                                 :coord-ndims)))))
       (should (= expected-count (length chunks)))
       (should (cl-every (lambda (row) (plist-get row :chunk-addr))
                         chunks))
       (when expected-last-scaled-offsets
         (should (equal expected-last-scaled-offsets
                        (plist-get (car (last chunks))
                                   :scaled-offsets))))))))

(ert-deftest hdf5-poke-process-decodes-chunk-index-families ()
  (hdf5-poke-process-test--assert-chunk-index
   "chunk_v1_btree.h5" 1400 3 "v1-btree" 4)
  (hdf5-poke-process-test--assert-chunk-index
   "chunk_fixed_array.h5" 463 2 "fixed-array" 4)
  (hdf5-poke-process-test--assert-chunk-index
   "chunk_extensible_array.h5" 463 2 "extensible-array" 3)
  (hdf5-poke-process-test--assert-chunk-index
   "chunk_v2_btree.h5" 463 3 "v2-btree" 4 '(1 1) 2))

(ert-deftest hdf5-poke-process-previews-small-contiguous-dataset ()
  (hdf5-poke-process-test--with-session
   "old_style_group.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-preview-dataset-at 1832 128 "/group/dset_00"))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-data:old_style_group.h5@1832*"
       (should (derived-mode-p 'hdf5-poke-dataset-preview-mode))
       (should (save-excursion
                 (goto-char (point-min))
                 (search-forward "(0 1 2 3)" nil t)))))))

(ert-deftest hdf5-poke-process-resolves-path-commands ()
  (hdf5-poke-process-test--with-session
   "old_style_group.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-open-path "/group/dset_00"))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-messages:old_style_group.h5@1832*"
       (should (derived-mode-p 'hdf5-poke-message-list-mode))
       (should (equal hdf5-poke--object-path "/group/dset_00")))
     (with-current-buffer session
       (hdf5-poke-preview-path "/group/dset_00" 128))
     (hdf5-poke-process-test--wait session)
     (with-current-buffer "*hdf5-poke-data:old_style_group.h5@1832*"
       (should (derived-mode-p 'hdf5-poke-dataset-preview-mode))
       (should (save-excursion
                 (goto-char (point-min))
                 (search-forward "Datatype: int16" nil t)))
       (should (save-excursion
                 (goto-char (point-min))
                 (search-forward "(0 1 2 3)" nil t)))))))

(ert-deftest hdf5-poke-process-renders-nested-datatype-tree ()
  (hdf5-poke-process-test--with-session
   "nested_datatypes.h5"
   (lambda (session)
     (with-current-buffer session
       (hdf5-poke-open-path "/compound"))
     (hdf5-poke-process-test--wait session)
     (let* ((message-buffer
             (cl-find-if
              (lambda (buffer)
                (string-prefix-p
                 "*hdf5-poke-messages:nested_datatypes.h5@"
                 (buffer-name buffer)))
              (buffer-list)))
            (datatype-row nil)
            payload size name)
       (should message-buffer)
       (with-current-buffer message-buffer
         (setq datatype-row
               (cl-find-if
                (lambda (row)
                  (= (plist-get row :type) 3))
                (mapcar #'car tabulated-list-entries)))
         (should datatype-row)
         (setq payload (plist-get datatype-row :payload-offset)
               size (plist-get datatype-row :size)
               name (plist-get datatype-row :name)))
       (with-current-buffer session
         (hdf5-poke-message-detail-at 3 payload size name))
       (hdf5-poke-process-test--wait session)
       (with-current-buffer
           (format "*hdf5-poke-message:nested_datatypes.h5:Datatype@%s*"
                   payload)
         (should (derived-mode-p 'hdf5-poke-message-detail-mode))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "Datatype tree" nil t)))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "inner" nil t)))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "samples" nil t)))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "array-base" nil t)))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "Payload bytes @" nil t)))
         (should (save-excursion
                   (goto-char (point-min))
                   (search-forward "GNU poke datatype view" nil t))))))))

;;; hdf5-poke-process-test.el ends here
