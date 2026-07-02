;;; hdf5-poke-test.el --- Tests for hdf5-poke.el -*- lexical-binding: t; -*-

;; SPDX-License-Identifier: GPL-3.0-or-later

;;; Code:

(require 'ert)
(load-file (expand-file-name "../emacs/hdf5-poke.el"
                             (file-name-directory
                              (or load-file-name buffer-file-name))))

(ert-deftest hdf5-poke-protocol-parses-records-and-raw ()
  (let (seen-records seen-raws seen-errors)
    (with-temp-buffer
      (hdf5-poke-process-mode)
      (setq-local hdf5-poke--pending-requests (make-hash-table :test 'eql))
      (puthash 7
               (list :session (current-buffer)
                     :callback (lambda (records raws errors)
                                 (setq seen-records records
                                       seen-raws raws
                                       seen-errors errors)))
               hdf5-poke--pending-requests)
      (dolist (line '("@@HDF5-POKE-BEGIN 7"
                      "(:record superblock :offset 0 :version 2 :root-offset 48)"
                      "@@HDF5-POKE-RAW-BEGIN 7"
                      "raw line one"
                      "raw line two"
                      "@@HDF5-POKE-RAW-END 7"
                      "@@HDF5-POKE-END 7"))
        (hdf5-poke--protocol-handle-line line)))
    (should (equal seen-records
                   '((:record superblock :offset 0 :version 2 :root-offset 48))))
    (should (equal seen-raws '("raw line one\nraw line two")))
    (should-not seen-errors)))

(ert-deftest hdf5-poke-renders-message-table-with-layout-action ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (table-name "*hdf5-poke-messages:file.h5@195*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-message-list
           195
           '((:record object-header :offset 195 :version 2
                      :chunk-offset 219 :chunk-size 256)
             (:record message :index 4 :type 8 :name "Data Layout"
                      :prefix-offset 297 :payload-offset 301
                      :size 23 :flags 0 :creation-order nil)
             (:record layout :message-index 4 :payload-offset 301
                      :version 3 :class "chunked" :ndims 3
                      :chunk-index 479))
           nil)
          (with-current-buffer table-name
            (should (= 1 (length tabulated-list-entries)))
            (should (equal (plist-get (caar tabulated-list-entries) :payload-offset)
                           301))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "chunk index 479" nil t)))))
      (when (get-buffer table-name) (kill-buffer table-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-chunk-index-table ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (table-name "*hdf5-poke-chunks:file.h5@479*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-chunk-index
           479
           3
           '((:record chunk-index :offset 479 :kind "v1-btree"
                      :node-type 1 :level 0 :entries 1 :ndims 3)
             (:record chunk :index 0 :source "v1-btree"
                      :chunk-addr 3255 :chunk-size 64
                      :filter-mask 1 :offsets (0 0 0)))
           nil
           '(4 4 4))
          (with-current-buffer table-name
            (should (= 1 (length tabulated-list-entries)))
            (should (equal hdf5-poke--chunk-index-offset 479))
            (should (equal hdf5-poke--chunk-index-ndims 3))
            (let ((row-id (caar tabulated-list-entries)))
              (should (eq (plist-get row-id :record) 'chunk))
              (should (= (plist-get row-id :chunk-addr) 3255))
              (should (equal (plist-get row-id :offsets) '(0 0 0))))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Kind: v1-btree" nil t)))))
      (when (get-buffer table-name) (kill-buffer table-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-scaled-and-logical-chunk-offsets ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (table-name "*hdf5-poke-chunks:file.h5@463*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-chunk-index
           463
           3
           '((:record chunk-index :offset 463 :kind "v2-btree"
                      :record-type 11 :depth 0 :root 4096
                      :root-records 1 :total-records 1
                      :ndims 3 :coord-ndims 2)
             (:record chunk :index 0 :source "v2-btree"
                      :chunk-addr 2105 :chunk-size 19
                      :filter-mask 0 :scaled-offsets (1 1)))
           nil
           '(2 2 4))
          (with-current-buffer table-name
            (let* ((entry (car tabulated-list-entries))
                   (columns (cadr entry)))
              (should (string-match-p "scaled=(1 1)"
                                      (aref columns 5)))
              (should (string-match-p "logical=(2 2)"
                                      (aref columns 5))))))
      (when (get-buffer table-name) (kill-buffer table-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-infers-object-kind-from-message-records ()
  (should (eq (hdf5-poke--records-object-kind
               '((:record object-header :offset 48)
                 (:record message :type 2 :name "Link Info")))
              'group))
  (should (eq (hdf5-poke--records-object-kind
               '((:record object-header :offset 1832)
                 (:record message :type 1 :name "Dataspace")
                 (:record layout :class "contiguous")))
              'dataset))
  (should (eq (hdf5-poke--records-object-kind
               '((:record object-header :offset 99)))
              'unknown)))

(ert-deftest hdf5-poke-normalizes-absolute-paths ()
  (should (equal (hdf5-poke--normalize-path "/") "/"))
  (should (equal (hdf5-poke--normalize-path "/group/dset/") "/group/dset"))
  (should (equal (hdf5-poke--path-components "/group/dset")
                 '("group" "dset")))
  (should-error (hdf5-poke--normalize-path "group/dset") :type 'user-error))

(ert-deftest hdf5-poke-renders-structured-message-detail ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (buffer-name "*hdf5-poke-message:file.h5:Dataspace@223*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-message-detail
           1 223
           '((:record message-detail :type 1 :name "Dataspace"
                      :payload-offset 223 :size 36)
             (:record dataspace :version 2 :ndims 2 :flags 1
                      :space-type "simple" :dims (8 8)))
           '("H5O_msg_sdspace {...}")
           nil
           "Dataspace")
          (with-current-buffer buffer-name
            (should (derived-mode-p 'hdf5-poke-message-detail-mode))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Structured" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "dims                 (8 8)" nil t)))))
      (when (get-buffer buffer-name) (kill-buffer buffer-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-empty-raw-placeholder ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (buffer-name "*hdf5-poke-message:file.h5:Unknown@777*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-message-detail
           99 777
           '((:record message-detail :type 99 :name "Unknown"
                      :payload-offset 777 :size 0))
           '("")
           nil
           "Unknown")
          (with-current-buffer buffer-name
            (should (derived-mode-p 'hdf5-poke-message-detail-mode))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward
                       "No raw output returned by GNU poke." nil t)))))
      (when (get-buffer buffer-name) (kill-buffer buffer-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-nested-datatype-tree ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (buffer-name "*hdf5-poke-message:file.h5:Datatype@500*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-message-detail
           3 500
           '((:record message-detail :type 3 :name "Datatype"
                      :payload-offset 500 :size 96)
             (:record datatype :version 3 :class 6 :class-name "compound"
                      :element-size 16 :flags 54)
             (:record datatype-node :path "$" :depth 0 :offset 500
                      :version 3 :class 6 :class-name "compound"
                      :element-size 16 :flags 54 :members 2)
             (:record datatype-member :parent-path "$" :child-path "$.id"
                      :depth 1 :index 0 :name "id" :member-offset 0)
             (:record datatype-node :path "$.id" :depth 1 :offset 520
                      :version 3 :class 0 :class-name "fixed-point"
                      :element-size 4 :flags 48 :byte-order "little-endian"
                      :signed nil :bit-offset 0 :bit-precision 32)
             (:record datatype-member :parent-path "$" :child-path "$.samples"
                      :depth 1 :index 1 :name "samples" :member-offset 4)
             (:record datatype-node :path "$.samples" :depth 1 :offset 532
                      :version 3 :class 10 :class-name "array"
                      :element-size 6 :flags 58 :dims (3))
             (:record datatype-base :parent-path "$.samples"
                      :child-path "$.samples[]" :depth 2
                      :role "array-base")
             (:record datatype-node :path "$.samples[]" :depth 2 :offset 552
                      :version 3 :class 0 :class-name "fixed-point"
                      :element-size 2 :flags 48 :byte-order "little-endian"
                      :signed t :bit-offset 0 :bit-precision 16))
           '("H5O_msg_dtype {...}")
           nil
           "Datatype")
          (with-current-buffer buffer-name
            (should (derived-mode-p 'hdf5-poke-message-detail-mode))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Datatype tree" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "id @0: fixed-point" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "samples @4: array" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "array-base: fixed-point" nil t)))))
      (when (get-buffer buffer-name) (kill-buffer buffer-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-dataset-preview-values ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (buffer-name "*hdf5-poke-data:file.h5@1832*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-dataset-preview
           1832
           '((:record dataset :object-header-offset 1832 :max-bytes 128)
             (:record dataspace :version 1 :ndims 1 :flags 1 :dims (4))
             (:record datatype :version 1 :class 0
                      :class-name "fixed-point" :element-size 2
                      :flags 2064)
             (:record layout :message-index 0 :payload-offset 1928
                      :version 3 :class "contiguous"
                      :data-addr 2432 :data-size 8)
             (:record dataset-preview :layout "contiguous"
                      :data-offset 2432 :size 8 :max-bytes 128
                      :dtype-class 0 :element-size 2 :signed t
                      :supported t :reason nil)
             (:record data-bytes :offset 2432 :size 8
                      :bytes (0 0 1 0 2 0 3 0)))
           nil
           "/group/dset_00")
          (with-current-buffer buffer-name
            (should (derived-mode-p 'hdf5-poke-dataset-preview-mode))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Dimensions: (4)" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Datatype: int16" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "(0 1 2 3)" nil t)))))
      (when (get-buffer buffer-name) (kill-buffer buffer-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-unsigned-dataset-preview-values ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (buffer-name "*hdf5-poke-data:file.h5@2048*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-dataset-preview
           2048
           '((:record dataset :object-header-offset 2048 :max-bytes 128)
             (:record dataspace :version 1 :ndims 1 :flags 1 :dims (2))
             (:record datatype :version 1 :class 0
                      :class-name "fixed-point" :element-size 1
                      :flags 0)
             (:record dataset-preview :layout "contiguous"
                      :data-offset 4096 :size 2 :max-bytes 128
                      :dtype-class 0 :element-size 1 :signed nil
                      :supported t :reason nil)
             (:record data-bytes :offset 4096 :size 2
                      :bytes (0 255)))
           nil
           "/bytes")
          (with-current-buffer buffer-name
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Datatype: uint8" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "(0 255)" nil t)))))
      (when (get-buffer buffer-name) (kill-buffer buffer-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-link-table-with-openable-link-id ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (table-name "*hdf5-poke-links:file.h5@48*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-link-list
           48
           '((:record links :object-header-offset 48)
             (:record link :name "DirectChunkData" :message-index 2
                      :payload-offset 103 :source "compact"
                      :kind "hard" :target 195 :note nil))
           nil)
          (with-current-buffer table-name
            (should (= 1 (length tabulated-list-entries)))
            (let ((row-id (caar tabulated-list-entries)))
              (should (eq (plist-get row-id :record) 'link))
              (should (= (plist-get row-id :target) 195))
              (should (equal (plist-get row-id :name) "DirectChunkData")))))
      (when (get-buffer table-name) (kill-buffer table-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-link-table-with-breadcrumbs ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (table-name "*hdf5-poke-links:file.h5@195*"))
    (unwind-protect
        (with-current-buffer session
          (hdf5-poke-mode)
          (setq-local hdf5-poke--target-file "/tmp/file.h5")
          (setq-local hdf5-poke--process-buffer (current-buffer))
          (hdf5-poke--render-link-list
           195
           '((:record links :object-header-offset 195)
             (:record link :name "data" :message-index 2
                      :payload-offset 103 :source "compact"
                      :kind "hard" :target 300 :note nil))
           nil
           "/group"
           (list (cons "/" 48) (cons "/group" 195)))
          (with-current-buffer table-name
            (should (equal hdf5-poke--object-path "/group"))
            (should (equal hdf5-poke--path-stack
                           (list (cons "/" 48) (cons "/group" 195))))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "Open messages" nil t)))))
      (when (get-buffer table-name) (kill-buffer table-name))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-renders-tree-buffer ()
  (let ((session (generate-new-buffer " *hdf5-poke-test-session*"))
        (tree (generate-new-buffer "*hdf5-poke-tree:file.h5*")))
    (unwind-protect
        (progn
          (with-current-buffer session
            (hdf5-poke-mode)
            (setq-local hdf5-poke--target-file "/tmp/file.h5")
            (setq-local hdf5-poke--process-buffer (current-buffer)))
          (with-current-buffer tree
            (hdf5-poke-tree-mode)
            (setq-local hdf5-poke--origin-session session)
            (setq-local hdf5-poke--tree-root
                        (list :name "/" :path "/" :target 48
                              :loaded t :expanded t
                              :stack (list (cons "/" 48))
                              :children
                              (list (list :name "group"
                                          :path "/group"
                                          :target 195
                                          :kind 'unknown
                                          :loaded nil
                                          :expanded nil
                                          :children nil
                                          :stack (list (cons "/" 48)
                                                       (cons "/group" 195))))))
            (hdf5-poke--tree-render)
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "group  @195" nil t)))
            (should (save-excursion
                      (goto-char (point-min))
                      (search-forward "[?] group" nil t)))
            (goto-char (point-min))
            (search-forward "group")
            (should (equal (plist-get (hdf5-poke--tree-node-at-point) :path)
                           "/group"))))
      (when (buffer-live-p tree) (kill-buffer tree))
      (when (buffer-live-p session) (kill-buffer session)))))

(ert-deftest hdf5-poke-marks-tree-hard-link-cycles ()
  (let* ((parent (list :name "/" :path "/" :target 48
                       :kind 'group
                       :stack (list (cons "/" 48))))
         (children (hdf5-poke--tree-children-from-records
                    parent
                    '((:record link :name "again" :kind "hard"
                       :target 48 :source "compact"))))
         (child (car children)))
    (should (plist-get child :cycle))
    (should (eq (plist-get child :kind) 'cycle))
    (should (plist-get child :loaded))
    (should (equal (plist-get child :cycle-target) "/"))))

(ert-deftest hdf5-poke-times-out-pending-request ()
  (let ((process-buffer (generate-new-buffer " *hdf5-poke-test-proc*"))
        (session (generate-new-buffer " *hdf5-poke-test-session*"))
        (hdf5-poke-request-timeout 15)
        messages)
    (unwind-protect
        (progn
          (with-current-buffer session (hdf5-poke-mode))
          (with-current-buffer process-buffer
            (setq-local hdf5-poke--pending-requests (make-hash-table :test 'eql))
            (puthash 7
                     (list :callback #'ignore :session session
                           :title "Overview" :timer nil)
                     hdf5-poke--pending-requests))
          (cl-letf (((symbol-function 'message)
                     (lambda (fmt &rest args)
                       (push (apply #'format fmt args) messages))))
            (hdf5-poke--request-timeout process-buffer 7))
          (should (= 0 (hash-table-count
                        (buffer-local-value 'hdf5-poke--pending-requests
                                            process-buffer))))
          (should (cl-some (lambda (m) (string-match-p "no response" m))
                           messages)))
      (kill-buffer process-buffer)
      (kill-buffer session))))

(ert-deftest hdf5-poke-flushes-pending-requests-on-process-death ()
  (let ((process-buffer (generate-new-buffer " *hdf5-poke-test-proc*"))
        (session (generate-new-buffer " *hdf5-poke-test-session*"))
        messages)
    (unwind-protect
        (progn
          (with-current-buffer session (hdf5-poke-mode))
          (with-current-buffer process-buffer
            (setq-local hdf5-poke--pending-requests (make-hash-table :test 'eql))
            (puthash 1 (list :title "A" :session session :timer nil)
                     hdf5-poke--pending-requests)
            (puthash 2 (list :title "B" :session session :timer nil)
                     hdf5-poke--pending-requests)
            (cl-letf (((symbol-function 'message)
                       (lambda (fmt &rest args)
                         (push (apply #'format fmt args) messages))))
              (hdf5-poke--flush-pending-requests "GNU poke process exit")))
          (should (= 0 (hash-table-count
                        (buffer-local-value 'hdf5-poke--pending-requests
                                            process-buffer))))
          (should (= 2 (length messages))))
      (kill-buffer process-buffer)
      (kill-buffer session))))

(ert-deftest hdf5-poke-cancels-timer-when-response-completes ()
  (let ((process-buffer (generate-new-buffer " *hdf5-poke-test-proc*"))
        (session (generate-new-buffer " *hdf5-poke-test-session*"))
        seen fired)
    (unwind-protect
        (with-current-buffer process-buffer
          (hdf5-poke-process-mode)
          (setq-local hdf5-poke--pending-requests (make-hash-table :test 'eql))
          (let ((timer (run-at-time 100 nil (lambda () (setq fired t)))))
            (puthash 9
                     (list :session session
                           :callback (lambda (records _raws _errors)
                                       (setq seen records))
                           :title "Overview"
                           :timer timer)
                     hdf5-poke--pending-requests)
            (dolist (line '("@@HDF5-POKE-BEGIN 9"
                            "(:record root :offset 48)"
                            "@@HDF5-POKE-END 9"))
              (hdf5-poke--protocol-handle-line line))
            (should (equal seen '((:record root :offset 48))))
            (should-not (memq timer timer-list))
            (should-not fired)))
      (kill-buffer process-buffer)
      (kill-buffer session))))

;;; hdf5-poke-test.el ends here
