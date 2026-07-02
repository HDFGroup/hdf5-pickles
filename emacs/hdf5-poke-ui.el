;;; hdf5-poke-ui.el --- HDF5 poke inspector UI -*- lexical-binding: t; -*-

;; Copyright (C) 2026 The HDF Group.

;; Author: HDF Group
;; Keywords: data, files, tools
;; SPDX-License-Identifier: GPL-3.0-or-later

;;; Commentary:

;; The HDF5 poke inspector UI: major modes and keymaps, buffer renderers, the
;; expandable path tree, and the interactive commands.  These layers are
;; mutually recursive -- a rendered button triggers a command, and a command
;; renders -- so they live in one file and need no forward declarations.
;;
;; Foundational state, the GNU poke process/protocol, and pure helpers live in
;; `hdf5-poke-core'.

;;; Code:

(require 'cl-lib)
(require 'button)
(require 'comint)
(require 'subr-x)
(require 'tabulated-list)
(require 'hdf5-poke-core)

;;;; Key bindings

;; Each mode's keys live in one data table.  The keymap and the on-screen
;; "Keys: ..." hint are both derived from it, so they cannot drift apart.

(defun hdf5-poke--make-keymap (specs &optional parent)
  "Build a sparse keymap binding SPECS, optionally inheriting PARENT.
Each spec is (KEY COMMAND [LABEL]); the LABEL is used only for key hints."
  (let ((map (make-sparse-keymap)))
    (when parent
      (set-keymap-parent map parent))
    (dolist (spec specs map)
      (keymap-set map (car spec) (cadr spec)))))

(defun hdf5-poke--key-hints (specs)
  "Return a compact \"Keys: ...\" string built from labelled SPECS.
Specs whose LABEL is nil are bound but omitted from the hint."
  (concat "Keys: "
          (mapconcat #'identity
                     (delq nil
                           (mapcar (lambda (spec)
                                     (when (caddr spec)
                                       (format "%s %s" (car spec) (caddr spec))))
                                   specs))
                     ", ")
          "."))

(defconst hdf5-poke-mode-keys
  '(("s" hdf5-poke-refresh-overview "refresh overview")
    ("S" hdf5-poke-set-superblock-offset "set superblock offset")
    ("r" hdf5-poke-root-object-header "root messages")
    ("b" hdf5-poke-browse "browse root")
    ("T" hdf5-poke-tree "tree")
    ("P" hdf5-poke-open-path "path messages")
    ("B" hdf5-poke-links-path "path links")
    ("D" hdf5-poke-preview-path "path preview")
    ("L" hdf5-poke-links "links")
    ("m" hdf5-poke-object-header-messages "messages")
    ("o" hdf5-poke-object-header-messages)
    ("c" hdf5-poke-chunk-index "chunk index")
    ("t" hdf5-poke-v1-btree "v1 b-tree")
    ("n" hdf5-poke-set-v1-btree-ndims "set v1 ndims")
    ("v" hdf5-poke-pretty-print "raw/pretty-print")
    ("g" hdf5-poke-pretty-print)
    ("l" hdf5-poke-load-pickle "load pickle")
    ("e" hdf5-poke-eval "eval")
    ("w" hdf5-poke-write-expression "write")
    ("p" hdf5-poke-switch-to-process-buffer "process")
    ("q" quit-window "quit"))
  "Bindings and key-hint labels for `hdf5-poke-mode'.
Each entry is (KEY COMMAND [LABEL]); entries without a LABEL are bound but
omitted from the generated key hint.")

(defconst hdf5-poke-tree-mode-keys
  '(("TAB" hdf5-poke-tree-toggle "expand/collapse")
    ("<tab>" hdf5-poke-tree-toggle)
    ("RET" hdf5-poke-tree-open "messages")
    ("m" hdf5-poke-tree-open)
    ("g" hdf5-poke-tree-refresh "refresh")
    ("d" hdf5-poke-tree-preview "preview")
    ("L" hdf5-poke-tree-open-links "links")
    ("p" hdf5-poke-switch-to-process-buffer "process")
    ("q" quit-window "quit"))
  "Bindings and key-hint labels for `hdf5-poke-tree-mode'.
See `hdf5-poke-mode-keys' for the entry format.")

;;;; Major modes and keymaps

(defvar hdf5-poke-mode-map (hdf5-poke--make-keymap hdf5-poke-mode-keys)
  "Keymap for `hdf5-poke-mode'.")

(define-derived-mode hdf5-poke-mode special-mode "HDF5-Poke"
  "Major mode for an HDF5 GNU poke inspector buffer.")

(defvar-keymap hdf5-poke-message-list-mode-map
  :doc "Keymap for HDF5 object-header message tables."
  :parent tabulated-list-mode-map
  "RET" #'hdf5-poke-message-list-open
  "g" #'hdf5-poke-revert-object-header-messages
  "L" #'hdf5-poke-links-for-current-object-header
  "d" #'hdf5-poke-preview-current-object-header
  "v" #'hdf5-poke-pretty-print-current-object-header
  "p" #'hdf5-poke-switch-to-process-buffer)

(define-derived-mode hdf5-poke-message-list-mode tabulated-list-mode
  "HDF5-Messages"
  "Major mode for HDF5 object-header message tables."
  (setq tabulated-list-format
        [("Index" 7 t)
         ("Type" 7 t)
         ("Name" 30 t)
         ("Prefix" 10 t)
         ("Payload" 10 t)
         ("Size" 8 t)
         ("Flags" 8 t)
         ("Crt" 8 t)])
  (setq tabulated-list-padding 2)
  (tabulated-list-init-header))

(defvar-keymap hdf5-poke-link-list-mode-map
  :doc "Keymap for HDF5 link tables."
  :parent tabulated-list-mode-map
  "RET" #'hdf5-poke-link-list-open
  "g" #'hdf5-poke-revert-links
  "m" #'hdf5-poke-object-header-messages-for-current-links
  "d" #'hdf5-poke-preview-current-object-header
  "v" #'hdf5-poke-pretty-print-current-object-header
  "p" #'hdf5-poke-switch-to-process-buffer)

(define-derived-mode hdf5-poke-link-list-mode tabulated-list-mode
  "HDF5-Links"
  "Major mode for HDF5 hard-link tables."
  (setq tabulated-list-format
        [("Name/Storage" 28 t)
         ("Kind" 14 t)
         ("Target" 10 t)
         ("Message" 8 t)
         ("Note" 32 t)])
  (setq tabulated-list-padding 2)
  (tabulated-list-init-header))

(defvar-keymap hdf5-poke-chunk-list-mode-map
  :doc "Keymap for HDF5 chunk-index tables."
  :parent tabulated-list-mode-map
  "RET" #'hdf5-poke-chunk-list-open
  "g" #'hdf5-poke-revert-chunk-index
  "v" #'hdf5-poke-pretty-print-current-chunk-index
  "p" #'hdf5-poke-switch-to-process-buffer)

(define-derived-mode hdf5-poke-chunk-list-mode tabulated-list-mode
  "HDF5-Chunks"
  "Major mode for HDF5 chunk-index tables."
  (setq tabulated-list-format
        [("Index" 7 t)
         ("Source" 18 t)
         ("Address" 10 t)
         ("Size" 10 t)
         ("Filter" 8 t)
         ("Offsets" 48 t)])
  (setq tabulated-list-padding 2)
  (tabulated-list-init-header))

(define-derived-mode hdf5-poke-raw-mode special-mode "HDF5-Raw"
  "Major mode for protocol-delimited raw GNU poke output.")

(define-derived-mode hdf5-poke-message-detail-mode special-mode
  "HDF5-Message"
  "Major mode for structured HDF5 object-header message details.")

(defvar hdf5-poke-tree-mode-map
  (hdf5-poke--make-keymap hdf5-poke-tree-mode-keys special-mode-map)
  "Keymap for HDF5 path tree buffers.")

(define-derived-mode hdf5-poke-tree-mode special-mode
  "HDF5-Tree"
  "Major mode for an expandable HDF5 path tree.")

(define-derived-mode hdf5-poke-dataset-preview-mode special-mode
  "HDF5-Data"
  "Major mode for small read-only HDF5 dataset previews.")

;;;; Shared UI helpers

(defun hdf5-poke--insert-action (label action &rest args)
  "Insert a clickable LABEL that calls ACTION with ARGS."
  (insert-text-button label
                      'follow-link t
                      'action (lambda (_button)
                                (apply action args))))

(defun hdf5-poke--insert-breadcrumbs (path stack offset &optional mode)
  "Insert breadcrumb actions for PATH, STACK, and OFFSET.

MODE controls the sibling action: `messages' inserts an Open links action;
`links' inserts an Open messages action."
  (let ((stack (or stack (list (cons (or path "/") offset)))))
    (insert "\nPath\n"
            "----\n")
    (cl-loop for entry in stack
             for idx from 0
             do
             (when (> idx 0) (insert " / "))
             (let ((entry-path (car entry))
                   (entry-offset (cdr entry)))
               (hdf5-poke--insert-action
                (if (= idx 0) "/" (file-name-nondirectory entry-path))
                #'hdf5-poke-links-at
                entry-offset entry-path
                (hdf5-poke--path-stack-prefix stack idx))))
    (insert (format "  (%s @ %s)\n" (hdf5-poke--path-label path) offset))
    (pcase mode
      ('messages
       (hdf5-poke--insert-action "Open links" #'hdf5-poke-links-at
                                 offset path stack)
       (insert "\n"))
      ('links
       (hdf5-poke--insert-action "Open messages"
                                 #'hdf5-poke-object-header-messages-at
                                 offset path stack)
       (insert "\n")))))

(defun hdf5-poke--render-session (buffer file process-buffer)
  "Render the inspector BUFFER for FILE and PROCESS-BUFFER."
  (with-current-buffer buffer
    (hdf5-poke-mode)
    (setq-local hdf5-poke--target-file file)
    (setq-local hdf5-poke--process-buffer process-buffer)
    (setq-local hdf5-poke--superblock-offset hdf5-poke-default-superblock-offset)
    (setq-local hdf5-poke--object-kind-cache (make-hash-table :test 'equal))
    (setq-local hdf5-poke--path-cache (make-hash-table :test 'equal))
    (let ((inhibit-read-only t))
      (erase-buffer)
      (insert "HDF5 poke inspector\n"
              "===================\n\n"
              "File: " file "\n"
              "Poke buffer: " (buffer-name process-buffer) "\n"
              "Pickles: " (file-name-as-directory hdf5-poke-pickles-directory) "\n\n"
              (hdf5-poke--key-hints hdf5-poke-mode-keys) "\n"))))

;;;; Renderers

(defun hdf5-poke--render-errors (errors)
  "Insert protocol parser ERRORS, when present."
  (when errors
    (let ((inhibit-read-only t))
      (insert "\nProtocol parser errors:\n")
      (dolist (error errors)
        (insert "  " error "\n")))))

(defun hdf5-poke--render-overview (records errors)
  "Render the main overview from protocol RECORDS and ERRORS."
  (let ((superblock (hdf5-poke--record records 'superblock))
        (root (or (plist-get (hdf5-poke--record records 'superblock) :root-offset)
                  (plist-get (hdf5-poke--record records 'root) :offset)))
        (inhibit-read-only t))
    (unless superblock
      (user-error "No superblock record returned by GNU poke"))
    (erase-buffer)
    (insert "HDF5 poke overview\n"
            "==================\n\n"
            "File: " hdf5-poke--target-file "\n"
            "Poke buffer: " (buffer-name hdf5-poke--process-buffer) "\n"
            "Pickles: " (file-name-as-directory hdf5-poke-pickles-directory) "\n\n"
            "Superblock\n"
            "----------\n")
    (insert (format "Offset: %s\n" (hdf5-poke--field superblock :offset)))
    (insert (format "Version: %s\n" (hdf5-poke--field superblock :version)))
    (insert (format "Offset size: %s\n" (hdf5-poke--field superblock :sizeof-offsets)))
    (insert (format "Length size: %s\n" (hdf5-poke--field superblock :sizeof-lengths)))
    (insert (format "EOF address: %s\n" (hdf5-poke--field superblock :eof-addr)))
    (insert (format "Root object header: %s\n" (or root "")))
    (insert (format "Status flags: %s\n" (hdf5-poke--field superblock :status-flags)))
    (when (plist-member superblock :checksum)
      (insert (format "Checksum: %s\n" (hdf5-poke--field superblock :checksum))))
    (insert "\nActions\n"
            "-------\n")
    (hdf5-poke--insert-action "Refresh overview" #'hdf5-poke-refresh-overview)
    (insert "  ")
    (hdf5-poke--insert-action "Raw superblock"
                              #'hdf5-poke-raw-at "superblock"
                              (plist-get superblock :offset))
    (when root
      (insert "  ")
      (hdf5-poke--insert-action "Root messages"
                                #'hdf5-poke-object-header-messages-at
                                root "/" (list (cons "/" root)))
      (insert "  ")
      (hdf5-poke--insert-action "Root links"
                                #'hdf5-poke-links-at
                                root "/" (list (cons "/" root)))
      (insert "  ")
      (hdf5-poke--insert-action "Raw root"
                                #'hdf5-poke-raw-at "object-header" root))
    (insert "\n\n" (hdf5-poke--key-hints hdf5-poke-mode-keys) "\n")
    (hdf5-poke--render-errors errors)
    (goto-char (point-min))))

(defun hdf5-poke--render-message-list (offset records errors &optional path stack)
  "Render object-header message RECORDS for OFFSET."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-messages:%s@%s*" file offset)))
         (session (current-buffer))
         (header (hdf5-poke--record records 'object-header))
         (messages (hdf5-poke--records records 'message))
         (layouts (hdf5-poke--records records 'layout))
         (kind (hdf5-poke--records-object-kind records)))
    (hdf5-poke--remember-object-kind offset kind)
    (with-current-buffer buffer
      (hdf5-poke-message-list-mode)
      (setq-local hdf5-poke--origin-session session)
      (setq-local hdf5-poke--object-header-offset offset)
      (setq-local hdf5-poke--object-path path)
      (setq-local hdf5-poke--path-stack stack)
      (setq-local tabulated-list-entries
                  (mapcar
                   (lambda (message)
                     (let ((index (hdf5-poke--field message :index))
                           (row-id (append message
                                           (list :object-header-offset offset))))
                       (list row-id
                             (vector
                              index
                              (hdf5-poke--field message :type)
                              (hdf5-poke--field message :name)
                              (hdf5-poke--field message :prefix-offset)
                              (hdf5-poke--field message :payload-offset)
                              (hdf5-poke--field message :size)
                              (hdf5-poke--field message :flags)
                              (hdf5-poke--field message :creation-order)))))
                   messages))
      (setq-local header-line-format
                  (format "%s  object header %s  version %s  chunk %s+%s"
                          (hdf5-poke--path-label path)
                          offset
                          (hdf5-poke--field header :version)
                          (hdf5-poke--field header :chunk-offset)
                          (hdf5-poke--field header :chunk-size)))
      (let ((inhibit-read-only t))
        (erase-buffer))
      (tabulated-list-print t)
      (goto-char (point-max))
      (let ((inhibit-read-only t))
        (hdf5-poke--insert-breadcrumbs path stack offset 'messages))
      (hdf5-poke--insert-layout-actions layouts)
      (when errors
        (goto-char (point-max))
        (hdf5-poke--render-errors errors)))
    (pop-to-buffer buffer)))

(defun hdf5-poke--insert-layout-actions (layouts)
  "Insert layout/chunk-index actions for LAYOUTS in a message table."
  (when layouts
    (goto-char (point-max))
    (let ((inhibit-read-only t))
      (insert "\nLayout\n"
              "------\n")
      (dolist (layout layouts)
        (insert (format "Message %s: %s layout"
                        (hdf5-poke--field layout :message-index)
                        (hdf5-poke--field layout :class)))
        (when (plist-member layout :chunk-index)
          (insert (format ", chunk index %s"
                          (hdf5-poke--field layout :chunk-index))))
        (insert "\n")
        (when-let ((chunk-index (plist-get layout :chunk-index)))
          (insert "  ")
          (hdf5-poke--insert-action
           "Open chunk index"
           #'hdf5-poke-chunk-index-at chunk-index
           (plist-get layout :ndims)
           (plist-get layout :chunk-dims))
          (insert "\n"))
        (when (member (plist-get layout :class) '("compact" "contiguous"))
          (insert "  ")
          (hdf5-poke--insert-action
           "Preview data"
           #'hdf5-poke-preview-current-object-header)
          (insert "\n"))))))

(defun hdf5-poke--render-link-list (offset records errors &optional path stack)
  "Render link RECORDS for object header OFFSET."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-links:%s@%s*" file offset)))
         (session (current-buffer))
         (links (hdf5-poke--records records 'link))
         (storage (hdf5-poke--records records 'link-storage))
         (rows nil))
    (when (or links storage)
      (hdf5-poke--remember-object-kind offset 'group))
    (dolist (link links)
      (push (list (append link (list :object-header-offset offset))
                  (vector
                   (hdf5-poke--field link :name)
                   (hdf5-poke--field link :kind)
                   (hdf5-poke--field link :target)
                   (hdf5-poke--field link :message-index)
                   (hdf5-poke--field link :note)))
            rows))
    (dolist (item storage)
      (let ((note (string-join
                   (delq nil
                         (list
                          (and (plist-member item :fheap)
                               (format "fheap=%s" (hdf5-poke--field item :fheap)))
                          (and (plist-member item :name-btree)
                               (format "name-btree=%s" (hdf5-poke--field item :name-btree)))
                          (and (plist-member item :corder-btree)
                               (format "corder-btree=%s" (hdf5-poke--field item :corder-btree)))
                          (and (plist-member item :btree)
                               (format "btree=%s" (hdf5-poke--field item :btree)))
                          (and (plist-member item :heap)
                               (format "heap=%s" (hdf5-poke--field item :heap)))))
                   " ")))
        (push (list (append item (list :object-header-offset offset))
                    (vector
                     (hdf5-poke--field item :kind)
                     "storage"
                     ""
                     (hdf5-poke--field item :message-index)
                     (if (string-empty-p note)
                         (hdf5-poke--field item :status)
                       (concat (hdf5-poke--field item :status)
                               " " note))))
              rows)))
    (with-current-buffer buffer
      (hdf5-poke-link-list-mode)
      (setq-local hdf5-poke--origin-session session)
      (setq-local hdf5-poke--object-header-offset offset)
      (setq-local hdf5-poke--object-path path)
      (setq-local hdf5-poke--path-stack stack)
      (setq-local tabulated-list-entries (nreverse rows))
      (setq-local header-line-format
                  (format "Links for %s  object header %s"
                          (hdf5-poke--path-label path)
                          offset))
      (let ((inhibit-read-only t))
        (erase-buffer))
      (tabulated-list-print t)
      (goto-char (point-max))
      (let ((inhibit-read-only t))
        (hdf5-poke--insert-breadcrumbs path stack offset 'links))
      (when (or (null rows) errors)
        (goto-char (point-max))
        (let ((inhibit-read-only t))
          (when (null rows)
            (insert "\nNo links found for this object header.\n")))
        (hdf5-poke--render-errors errors)))
    (pop-to-buffer buffer)))

(defun hdf5-poke--logical-offsets (scaled dims)
  "Return logical offsets by multiplying SCALED by DIMS."
  (when (and scaled dims)
    (cl-mapcar #'* scaled (cl-subseq dims 0 (min (length scaled)
                                                 (length dims))))))

(defun hdf5-poke--chunk-offsets (chunk dims)
  "Return CHUNK offsets display using chunk DIMS."
  (cond
   ((plist-member chunk :scaled-offsets)
    (let* ((scaled (plist-get chunk :scaled-offsets))
           (logical (hdf5-poke--logical-offsets scaled dims)))
      (format "scaled=%s%s"
              (hdf5-poke--format-value scaled)
              (if logical
                  (format " logical=%s" (hdf5-poke--format-value logical))
                ""))))
   ((plist-member chunk :offsets)
    (format "logical=%s" (hdf5-poke--field chunk :offsets)))
   ((plist-member chunk :key-bytes)
    (hdf5-poke--field chunk :key-bytes))
   (t "")))

(defun hdf5-poke--chunk-index-summary (record)
  "Return a compact summary string for a chunk-index RECORD."
  (string-join
   (delq nil
         (list
          (and (plist-member record :record-type)
               (format "record-type=%s" (hdf5-poke--field record :record-type)))
          (and (plist-member record :node-type)
               (format "node-type=%s" (hdf5-poke--field record :node-type)))
          (and (plist-member record :level)
               (format "level=%s" (hdf5-poke--field record :level)))
          (and (plist-member record :depth)
               (format "depth=%s" (hdf5-poke--field record :depth)))
          (and (plist-member record :entries)
               (format "entries=%s" (hdf5-poke--field record :entries)))
          (and (plist-member record :root-records)
               (format "root-records=%s" (hdf5-poke--field record :root-records)))
          (and (plist-member record :total-records)
               (format "total-records=%s" (hdf5-poke--field record :total-records)))
          (and (plist-member record :elements)
               (format "elements=%s" (hdf5-poke--field record :elements)))
          (and (plist-member record :ndims)
               (format "ndims=%s" (hdf5-poke--field record :ndims)))
          (and (plist-member record :coord-ndims)
               (format "coord-ndims=%s"
                       (hdf5-poke--field record :coord-ndims)))))
   " "))

(defun hdf5-poke--render-chunk-index (offset ndims records errors &optional dims)
  "Render chunk-index RECORDS for OFFSET, NDIMS, and chunk DIMS."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-chunks:%s@%s*" file offset)))
         (session (current-buffer))
         (index (hdf5-poke--record records 'chunk-index))
         (chunks (hdf5-poke--records records 'chunk)))
    (with-current-buffer buffer
      (hdf5-poke-chunk-list-mode)
      (setq-local hdf5-poke--origin-session session)
      (setq-local hdf5-poke--chunk-index-offset offset)
      (setq-local hdf5-poke--chunk-index-ndims ndims)
      (setq-local hdf5-poke--chunk-index-dims dims)
      (setq-local hdf5-poke--chunk-index-record index)
      (setq-local tabulated-list-entries
                  (mapcar
                   (lambda (chunk)
                     (list (append chunk (list :chunk-index-offset offset))
                           (vector
                            (hdf5-poke--field chunk :index)
                            (hdf5-poke--field chunk :source)
                            (hdf5-poke--field chunk :chunk-addr)
                            (hdf5-poke--field chunk :chunk-size)
                            (hdf5-poke--field chunk :filter-mask)
                            (hdf5-poke--chunk-offsets chunk dims))))
                   chunks))
      (setq-local header-line-format
                  (format "Chunk index %s  %s  %s"
                          offset
                          (hdf5-poke--field index :kind)
                          (hdf5-poke--chunk-index-summary index)))
      (let ((inhibit-read-only t))
        (erase-buffer))
      (tabulated-list-print t)
      (goto-char (point-max))
      (let ((inhibit-read-only t))
        (insert "\nIndex\n"
                "-----\n")
        (insert (format "Kind: %s\n" (hdf5-poke--field index :kind)))
        (let ((summary (hdf5-poke--chunk-index-summary index)))
          (unless (string-empty-p summary)
            (insert summary "\n")))
        (when dims
          (insert (format "Chunk dims: %s\n"
                          (hdf5-poke--format-value dims))))
        (insert (format "Chunks shown: %d\n" (length chunks)))
        (when (null chunks)
          (insert "No concrete chunk records were returned.\n")))
      (hdf5-poke--render-errors errors))
    (pop-to-buffer buffer)))

(defun hdf5-poke--render-raw (kind offset raw-blocks errors)
  "Render RAW-BLOCKS for KIND at OFFSET."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-raw:%s:%s@%s*" file kind offset)))
         (session (current-buffer)))
    (with-current-buffer buffer
      (hdf5-poke-raw-mode)
      (setq-local hdf5-poke--origin-session session)
      (setq-local hdf5-poke--object-header-offset offset)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (format "Raw %s at %s\n" kind offset)
                (make-string (+ 8 (length kind) (length (format "%s" offset))) ?-)
                "\n\n")
        (insert (or (car raw-blocks) ""))
        (unless (bolp) (insert "\n"))
        (hdf5-poke--render-errors errors)
        (goto-char (point-min))))
    (pop-to-buffer buffer)))

(defun hdf5-poke--format-value (value)
  "Format protocol VALUE for detail buffers."
  (cond
   ((null value) "")
   ((stringp value) value)
   ((listp value) (prin1-to-string value))
   (t (format "%s" value))))

(defun hdf5-poke--insert-record-fields (record)
  "Insert RECORD as a field list."
  (let ((fields record))
    (while fields
      (let ((key (pop fields))
            (value (pop fields)))
        (unless (eq key :record)
          (insert (format "%-20s %s\n"
                          (substring (symbol-name key) 1)
                          (hdf5-poke--format-value value))))))))

(defun hdf5-poke--datatype-tree-record-p (record)
  "Return non-nil when RECORD belongs to the datatype tree protocol."
  (memq (plist-get record :record)
        '(datatype-node datatype-member datatype-base
                        datatype-enum-member datatype-truncated)))

(defun hdf5-poke--datatype-edge-map (records)
  "Return hash table mapping datatype child paths to edge RECORDS."
  (let ((edges (make-hash-table :test 'equal)))
    (dolist (record records edges)
      (when (memq (plist-get record :record)
                  '(datatype-member datatype-base))
        (puthash (plist-get record :child-path) record edges)))))

(defun hdf5-poke--datatype-enum-member-map (records)
  "Return hash table mapping datatype paths to enum member RECORD lists."
  (let ((members (make-hash-table :test 'equal)))
    (dolist (record records members)
      (when (eq (plist-get record :record) 'datatype-enum-member)
        (let ((path (plist-get record :path)))
          (puthash path
                   (append (gethash path members) (list record))
                   members))))))

(defun hdf5-poke--datatype-node-summary (node)
  "Return a compact summary for datatype NODE."
  (let ((items (delq
                nil
                (list
                 (format "size=%s" (hdf5-poke--field node :element-size))
                 (and (plist-member node :byte-order)
                      (format "order=%s" (hdf5-poke--field node :byte-order)))
                 (and (plist-member node :signed)
                      (if (plist-get node :signed) "signed" "unsigned"))
                 (and (plist-member node :bit-precision)
                      (format "precision=%s"
                              (hdf5-poke--field node :bit-precision)))
                 (and (plist-member node :members)
                      (format "members=%s" (hdf5-poke--field node :members)))
                 (and (plist-member node :dims)
                      (format "dims=%s" (hdf5-poke--field node :dims)))
                 (and (plist-member node :vlen-type)
                      (format "vlen=%s" (hdf5-poke--field node :vlen-type)))
                 (and (plist-member node :padding)
                      (format "padding=%s" (hdf5-poke--field node :padding)))
                 (and (plist-member node :charset)
                      (format "charset=%s" (hdf5-poke--field node :charset)))))))
    (string-join items ", ")))

(defun hdf5-poke--datatype-node-label (node edge)
  "Return display label for datatype NODE reached through EDGE."
  (cond
   ((eq (plist-get edge :record) 'datatype-member)
    (format "%s @%s"
            (hdf5-poke--field edge :name)
            (hdf5-poke--field edge :member-offset)))
   ((eq (plist-get edge :record) 'datatype-base)
    (hdf5-poke--field edge :role))
   (t
    (hdf5-poke--field node :path))))

(defun hdf5-poke--insert-datatype-tree (records)
  "Insert nested datatype tree RECORDS."
  (let* ((nodes (hdf5-poke--records records 'datatype-node))
         (edges (hdf5-poke--datatype-edge-map records))
         (enum-members (hdf5-poke--datatype-enum-member-map records))
         (truncated (hdf5-poke--records records 'datatype-truncated)))
    (when nodes
      (insert "\nDatatype tree\n"
              "-------------\n")
      (dolist (node nodes)
        (let* ((depth (or (plist-get node :depth) 0))
               (path (plist-get node :path))
               (edge (gethash path edges))
               (indent (make-string (* 2 depth) ?\s))
               (label (hdf5-poke--datatype-node-label node edge))
               (class (hdf5-poke--field node :class-name))
               (summary (hdf5-poke--datatype-node-summary node)))
          (insert indent label ": " class)
          (unless (string-empty-p summary)
            (insert " (" summary ")"))
          (insert "\n")
          (dolist (member (gethash path enum-members))
            (insert indent "  "
                    (hdf5-poke--field member :name)
                    " = "
                    (hdf5-poke--field member :value-bytes)
                    "\n"))))
      (dolist (item truncated)
        (insert (make-string (* 2 (or (plist-get item :depth) 0)) ?\s)
                "... "
                (hdf5-poke--field item :reason)
                "\n")))))

(defun hdf5-poke--insert-message-detail-actions (record)
  "Insert context actions for structured detail RECORD."
  (pcase (plist-get record :record)
    ('layout
     (when-let ((chunk-index (plist-get record :chunk-index)))
       (insert "  ")
       (hdf5-poke--insert-action "Open chunk index"
                                 #'hdf5-poke-chunk-index-at
                                 chunk-index
                                 (plist-get record :ndims)
                                 (plist-get record :chunk-dims))
       (insert "\n")))
    ('link-info
     (when-let ((btree (plist-get record :name-btree)))
       (insert "  ")
       (hdf5-poke--insert-action "Raw name B-tree"
                                 #'hdf5-poke-raw-at "bytes" btree 256)
       (insert "\n")))
    ('symbol-table
     (when-let ((btree (plist-get record :btree)))
       (insert "  ")
       (hdf5-poke--insert-action "Raw B-tree"
                                 #'hdf5-poke-raw-at "v1-btree" btree)
       (insert "\n")))))

(defun hdf5-poke--render-message-detail (type payload-offset records raw-blocks
                                              errors &optional name)
  "Render structured message detail RECORDS and RAW-BLOCKS."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-message:%s:%s@%s*"
                          file (or name type) payload-offset)))
         (session (current-buffer))
         (detail (hdf5-poke--record records 'message-detail))
         (structured (cl-remove-if
                      (lambda (record)
                        (eq (plist-get record :record) 'message-detail))
                      records))
         (generic-structured (cl-remove-if
                              #'hdf5-poke--datatype-tree-record-p
                              structured)))
    (with-current-buffer buffer
      (hdf5-poke-message-detail-mode)
      (setq-local hdf5-poke--origin-session session)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (format "Message %s at %s\n"
                        (or name (plist-get detail :name) type)
                        payload-offset)
                (make-string 40 ?-)
                "\n\n")
        (insert "Message\n"
                "-------\n")
        (hdf5-poke--insert-record-fields detail)
        (if generic-structured
            (progn
              (insert "\nStructured\n"
                      "----------\n")
              (dolist (record generic-structured)
                (insert (format "%s\n"
                                (capitalize
                                 (symbol-name (plist-get record :record)))))
                (hdf5-poke--insert-record-fields record)
                (hdf5-poke--insert-message-detail-actions record)
                (insert "\n")))
          (insert "\nNo structured decoder for this message type.\n"))
        (hdf5-poke--insert-datatype-tree structured)
        (insert "Raw\n"
                "---\n")
        (let ((raw (car raw-blocks)))
          (insert (if (and raw (> (length raw) 0))
                      raw
                    "No raw output returned by GNU poke.\n")))
        (unless (bolp) (insert "\n"))
        (hdf5-poke--render-errors errors)
        (goto-char (point-min))))
    (pop-to-buffer buffer)))

(defun hdf5-poke--u64-from-le-bytes (bytes)
  "Return unsigned integer represented by little-endian BYTES."
  (let ((value 0)
        (shift 0))
    (dolist (byte bytes value)
      (setq value (+ value (ash byte shift))
            shift (+ shift 8)))))

(defun hdf5-poke--signed-from-u64 (value nbytes)
  "Interpret VALUE as signed integer encoded in NBYTES."
  (let* ((bits (* nbytes 8))
         (limit (ash 1 bits))
         (sign (ash 1 (1- bits))))
    (if (>= value sign)
        (- value limit)
      value)))

(defun hdf5-poke--decode-fixed-point-values (bytes element-size signed)
  "Decode little-endian fixed-point BYTES using ELEMENT-SIZE and SIGNED."
  (let (values)
    (while (>= (length bytes) element-size)
      (let* ((raw (cl-subseq bytes 0 element-size))
             (unsigned (hdf5-poke--u64-from-le-bytes raw)))
        (push (if signed
                  (hdf5-poke--signed-from-u64 unsigned element-size)
                unsigned)
              values)
        (setq bytes (nthcdr element-size bytes))))
    (nreverse values)))

(defun hdf5-poke--preview-dims (records)
  "Return dataspace dimensions from preview RECORDS."
  (plist-get (hdf5-poke--record records 'dataspace) :dims))

(defun hdf5-poke--preview-element-count (dims values)
  "Return expected element count for DIMS, falling back to VALUES length."
  (cond
   ((and dims (listp dims))
    (if dims
        (apply #'* dims)
      1))
   (values (length values))
   (t 0)))

(defun hdf5-poke--preview-type-label (preview)
  "Return a compact datatype label for PREVIEW."
  (let ((class (plist-get preview :dtype-class))
        (size (plist-get preview :element-size))
        (signed (plist-get preview :signed)))
    (cond
     ((and (equal class 0) size)
      (format "%sint%d" (if signed "" "u") (* size 8)))
     ((equal class 1) (format "float%d" (* (or size 0) 8)))
     ((equal class 3) "string")
     (t (format "class %s" (hdf5-poke--field preview :dtype-class))))))

(defun hdf5-poke--preview-2d-rows (values dims)
  "Return 2D row lists for VALUES shaped by DIMS."
  (let ((rows (car dims))
        (cols (cadr dims))
        (row 0)
        result)
    (while (< row rows)
      (push (cl-subseq values (* row cols) (* (1+ row) cols))
            result)
      (setq row (1+ row)))
    (nreverse result)))

(defun hdf5-poke--format-preview-values (values dims)
  "Return display string for decoded preview VALUES with DIMS."
  (cond
   ((null values) nil)
   ((null dims)
    (hdf5-poke--format-value values))
   ((null (cdr dims))
    (hdf5-poke--format-value values))
   ((and (= (length dims) 2)
         (= (length values) (apply #'* dims)))
    (string-join
     (mapcar #'hdf5-poke--format-value
             (hdf5-poke--preview-2d-rows values dims))
     "\n"))
   (t
    (hdf5-poke--format-value values))))

(defun hdf5-poke--render-dataset-preview (offset records errors &optional path)
  "Render dataset preview RECORDS for object header OFFSET."
  (let* ((file (file-name-nondirectory hdf5-poke--target-file))
         (buffer (get-buffer-create
                  (format "*hdf5-poke-data:%s@%s*" file offset)))
         (session (current-buffer))
         (preview (hdf5-poke--record records 'dataset-preview))
         (bytes-record (hdf5-poke--record records 'data-bytes))
         (bytes (plist-get bytes-record :bytes))
         (element-size (plist-get preview :element-size))
         (signed (plist-get preview :signed))
         (dims (hdf5-poke--preview-dims records))
         (values (and bytes element-size
                      (member element-size '(1 2 4 8))
                      (hdf5-poke--decode-fixed-point-values
                       bytes element-size signed)))
         (value-display (hdf5-poke--format-preview-values values dims)))
    (when preview
      (hdf5-poke--remember-object-kind offset 'dataset))
    (with-current-buffer buffer
      (hdf5-poke-dataset-preview-mode)
      (setq-local hdf5-poke--origin-session session)
      (setq-local hdf5-poke--object-header-offset offset)
      (setq-local hdf5-poke--object-path path)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (format "Dataset preview %s\n"
                        (or path (format "@%s" offset)))
                "----------------\n\n")
        (insert "Shape\n"
                "-----\n")
        (insert (format "Dimensions: %s\n"
                        (if dims
                            (hdf5-poke--format-value dims)
                          "scalar or unknown")))
        (insert (format "Elements: %s\n"
                        (hdf5-poke--preview-element-count dims values)))
        (when preview
          (insert (format "Datatype: %s\n"
                          (hdf5-poke--preview-type-label preview))))
        (insert "\n")
        (dolist (record records)
          (unless (eq (plist-get record :record) 'data-bytes)
            (insert (format "%s\n"
                            (capitalize
                             (symbol-name (plist-get record :record)))))
            (hdf5-poke--insert-record-fields record)
            (insert "\n")))
        (if (plist-get preview :supported)
            (progn
              (insert "Values\n"
                      "------\n")
              (if value-display
                  (insert value-display "\n")
                (insert "No value decoder for this fixed-point element size.\n"))
              (insert "\nBytes\n"
                      "-----\n"
                      (hdf5-poke--format-value bytes)
                      "\n"))
          (insert "Preview unavailable: "
                  (hdf5-poke--field preview :reason)
                  "\n"))
        (hdf5-poke--render-errors errors)
        (goto-char (point-min))))
    (pop-to-buffer buffer)))



;;;; Path tree

(defun hdf5-poke--tree-buffer-name (file)
  "Return tree buffer name for FILE."
  (format "*hdf5-poke-tree:%s*" (file-name-nondirectory file)))

(defun hdf5-poke--tree-node-path (node)
  "Return NODE path."
  (plist-get node :path))

(defun hdf5-poke--tree-node-target (node)
  "Return NODE target object-header offset."
  (plist-get node :target))

(defun hdf5-poke--tree-node-stack (node)
  "Return breadcrumb stack for NODE."
  (plist-get node :stack))

(defun hdf5-poke--tree-node-kind (node)
  "Return NODE object kind."
  (or (plist-get node :kind) 'unknown))

(defun hdf5-poke--tree-node-cycle-p (node)
  "Return non-nil when NODE is a hard-link cycle."
  (plist-get node :cycle))

(defun hdf5-poke--tree-node-at-point ()
  "Return the tree node at point."
  (or (get-text-property (point) 'hdf5-poke-tree-node)
      (get-text-property (line-beginning-position) 'hdf5-poke-tree-node)))

(defun hdf5-poke--tree-kind-label (kind)
  "Return display label for object KIND."
  (pcase kind
    ('group "group")
    ('dataset "dataset")
    ('cycle "cycle")
    (_ "?")))

(defun hdf5-poke--tree-insert-node (node depth)
  "Insert NODE and expanded descendants at DEPTH."
  (let* ((children (plist-get node :children))
         (loaded (plist-get node :loaded))
         (expanded (plist-get node :expanded))
         (target (hdf5-poke--tree-node-target node))
         (name (plist-get node :name))
         (line-start (point))
         (kind (hdf5-poke--tree-node-kind node))
         (cycle (hdf5-poke--tree-node-cycle-p node))
         (marker (cond
                  (cycle "[!]")
                  ((eq kind 'dataset) "   ")
                  ((not loaded) "[+]")
                  ((and children expanded) "[-]")
                  (children "[+]")
                  (loaded "   ")
                  (t "[+]"))))
    (insert (make-string (* 2 depth) ?\s))
    (insert marker " [" (hdf5-poke--tree-kind-label kind) "] ")
    (insert-text-button name
                        'follow-link t
                        'action (lambda (_button)
                                  (hdf5-poke-object-header-messages-at
                                   target
                                   (hdf5-poke--tree-node-path node)
                                   (hdf5-poke--tree-node-stack node))))
    (insert (format "  @%s" target))
    (when cycle
      (insert (format " -> %s" (plist-get node :cycle-target))))
    (insert "\n")
    (add-text-properties line-start (point)
                         (list 'hdf5-poke-tree-node node))
    (when expanded
      (dolist (child children)
        (hdf5-poke--tree-insert-node child (1+ depth))))))

(defun hdf5-poke--tree-render ()
  "Render the current tree buffer."
  (let ((inhibit-read-only t))
    (erase-buffer)
    (insert "HDF5 path tree\n"
            "==============\n\n")
    (if hdf5-poke--tree-root
        (hdf5-poke--tree-insert-node hdf5-poke--tree-root 0)
      (insert "No tree root loaded.\n"))
    (insert "\n" (hdf5-poke--key-hints hdf5-poke-tree-mode-keys) "\n")
    (goto-char (point-min))))

(defun hdf5-poke--tree-children-from-records (parent records)
  "Build child nodes for PARENT from link RECORDS."
  (let ((links (hdf5-poke--records records 'link))
        children)
    (dolist (link links)
      (when (and (equal (plist-get link :kind) "hard")
                 (plist-get link :target))
        (let* ((name (plist-get link :name))
               (path (hdf5-poke--child-path
                      (hdf5-poke--tree-node-path parent)
                      name))
              (target (plist-get link :target))
              (cycle-path (hdf5-poke--stack-path-for-offset
                           (hdf5-poke--tree-node-stack parent)
                           target))
              (cycle (and cycle-path t)))
          (push (list :name name
                      :path path
                      :target target
                      :kind (if cycle
                                'cycle
                              (or (hdf5-poke--cached-object-kind target)
                                  'unknown))
                      :source (plist-get link :source)
                      :loaded cycle
                      :expanded nil
                      :children nil
                      :cycle cycle
                      :cycle-target cycle-path
                      :stack (append (hdf5-poke--tree-node-stack parent)
                                     (list (cons path target))))
                children))))
    (nreverse children)))

(defun hdf5-poke--tree-load-links (node)
  "Load NODE children with the link protocol."
  (let ((tree-buffer (current-buffer))
        (target (hdf5-poke--tree-node-target node)))
    (hdf5-poke--send-request
     "Tree Links"
     "hdf5_poke_emacs_links"
     (hdf5-poke--request-args target)
     (lambda (records _raws _errors)
       (when (buffer-live-p tree-buffer)
         (with-current-buffer tree-buffer
           (when (or (hdf5-poke--record records 'link)
                     (hdf5-poke--record records 'link-storage))
             (setf (plist-get node :kind) 'group)
             (hdf5-poke--remember-object-kind target 'group))
           (setf (plist-get node :children)
                 (hdf5-poke--tree-children-from-records node records))
           (setf (plist-get node :loaded) t)
           (setf (plist-get node :expanded)
                 (and (not (eq (hdf5-poke--tree-node-kind node) 'dataset))
                      t))
           (hdf5-poke--tree-render)))))))

(defun hdf5-poke--tree-classify-and-load (node)
  "Classify NODE with object-header records, then load children when useful."
  (let ((tree-buffer (current-buffer))
        (target (hdf5-poke--tree-node-target node)))
    (hdf5-poke--send-request
     "Tree Object Header"
     "hdf5_poke_emacs_object_header"
     (hdf5-poke--request-args target)
     (lambda (records _raws _errors)
       (when (buffer-live-p tree-buffer)
         (with-current-buffer tree-buffer
           (let ((kind (hdf5-poke--records-object-kind records)))
             (setf (plist-get node :kind) kind)
             (hdf5-poke--remember-object-kind target kind)
             (if (eq kind 'dataset)
                 (progn
                   (setf (plist-get node :children) nil)
                   (setf (plist-get node :loaded) t)
                   (setf (plist-get node :expanded) nil)
                   (hdf5-poke--tree-render))
               (hdf5-poke--tree-load-links node)))))))))

(defun hdf5-poke--tree-load-children (node)
  "Load NODE children, classifying the object when needed."
  (cond
   ((hdf5-poke--tree-node-cycle-p node)
    (user-error "Hard-link cycle; already visited %s"
                (plist-get node :cycle-target)))
   ((eq (hdf5-poke--tree-node-kind node) 'dataset)
    (setf (plist-get node :loaded) t)
    (setf (plist-get node :expanded) nil)
    (hdf5-poke--tree-render))
   ((memq (hdf5-poke--tree-node-kind node) '(group unknown))
    (let ((cached (hdf5-poke--cached-object-kind
                   (hdf5-poke--tree-node-target node))))
      (if (and cached (not (eq cached 'unknown)))
          (progn
            (setf (plist-get node :kind) cached)
            (if (eq cached 'dataset)
                (progn
                  (setf (plist-get node :loaded) t)
                  (hdf5-poke--tree-render))
              (hdf5-poke--tree-load-links node)))
        (hdf5-poke--tree-classify-and-load node))))
   (t
    (hdf5-poke--tree-load-links node))))

(defun hdf5-poke-tree-toggle ()
  "Expand or collapse the tree node at point."
  (interactive)
  (let ((node (hdf5-poke--tree-node-at-point)))
    (unless node
      (user-error "No tree node at point"))
    (when (hdf5-poke--tree-node-cycle-p node)
      (user-error "Hard-link cycle; already visited %s"
                  (plist-get node :cycle-target)))
    (if (plist-get node :loaded)
        (progn
          (setf (plist-get node :expanded)
                (not (plist-get node :expanded)))
          (hdf5-poke--tree-render))
      (hdf5-poke--tree-load-children node))))

(defun hdf5-poke-tree-open ()
  "Open messages for the tree node at point."
  (interactive)
  (let ((node (hdf5-poke--tree-node-at-point)))
    (unless node
      (user-error "No tree node at point"))
    (hdf5-poke-object-header-messages-at
     (hdf5-poke--tree-node-target node)
     (hdf5-poke--tree-node-path node)
     (hdf5-poke--tree-node-stack node))))

(defun hdf5-poke-tree-open-links ()
  "Open links for the tree node at point."
  (interactive)
  (let ((node (hdf5-poke--tree-node-at-point)))
    (unless node
      (user-error "No tree node at point"))
    (when (eq (hdf5-poke--tree-node-kind node) 'dataset)
      (user-error "Selected node is a dataset, not a group"))
    (hdf5-poke-links-at
     (hdf5-poke--tree-node-target node)
     (hdf5-poke--tree-node-path node)
     (hdf5-poke--tree-node-stack node))))

(defun hdf5-poke-tree-preview ()
  "Preview dataset bytes for the tree node at point."
  (interactive)
  (let ((node (hdf5-poke--tree-node-at-point)))
    (unless node
      (user-error "No tree node at point"))
    (when (eq (hdf5-poke--tree-node-kind node) 'group)
      (user-error "Selected node is a group, not a dataset"))
    (hdf5-poke-preview-dataset-at
     (hdf5-poke--tree-node-target node)
     hdf5-poke-preview-max-bytes
     (hdf5-poke--tree-node-path node))))

(defun hdf5-poke-tree-refresh ()
  "Reload the current tree root."
  (interactive)
  (unless hdf5-poke--tree-root
    (user-error "No tree root loaded"))
  (setf (plist-get hdf5-poke--tree-root :loaded) nil)
  (setf (plist-get hdf5-poke--tree-root :children) nil)
  (setf (plist-get hdf5-poke--tree-root :expanded) nil)
  (hdf5-poke--tree-render)
  (hdf5-poke--tree-load-children hdf5-poke--tree-root))


;;;; Interactive commands

;;;###autoload
(defun hdf5-poke-open-file (file)
  "Open FILE in a direct GNU poke HDF5 inspector session."
  (interactive "fHDF5 file: ")
  (unless (executable-find hdf5-poke-program)
    (user-error "Cannot find GNU poke executable: %s" hdf5-poke-program))
  (unless (file-directory-p hdf5-poke-pickles-directory)
    (user-error "Pickles directory does not exist: %s" hdf5-poke-pickles-directory))
  (let* ((file (file-truename file))
         (base (file-name-nondirectory file))
         (process-buffer (get-buffer-create (format "*hdf5-poke-poke:%s*" base)))
         (session-buffer (get-buffer-create (format "*hdf5-poke:%s*" base)))
         (process-environment (hdf5-poke--environment)))
    (when-let ((old (get-buffer-process process-buffer)))
      (when (process-live-p old)
        (delete-process old)))
    (with-current-buffer process-buffer
      (let ((inhibit-read-only t))
        (erase-buffer))
      (hdf5-poke-process-mode)
      (setq-local hdf5-poke--inspector-buffer session-buffer))
    (apply #'make-comint-in-buffer
           (format "hdf5-poke:%s" base)
           process-buffer
           hdf5-poke-program
           nil
           (append (and hdf5-poke-no-init-file '("-q"))
                   (list "--quiet" file)))
    (with-current-buffer process-buffer
      (hdf5-poke-process-mode)
      (setq-local hdf5-poke--inspector-buffer session-buffer))
    (when-let ((process (get-buffer-process process-buffer)))
      (add-function :after (process-sentinel process)
                    #'hdf5-poke--process-sentinel))
    (hdf5-poke--render-session session-buffer file process-buffer)
    (setq hdf5-poke--last-session-buffer session-buffer)
    (with-current-buffer session-buffer
      (hdf5-poke--send "Bootstrap" (hdf5-poke--bootstrap-source))
      (hdf5-poke-refresh-overview))
    (pop-to-buffer session-buffer)))

;;;###autoload
(defun hdf5-poke-switch-to-process-buffer ()
  "Switch to the raw GNU poke process buffer for the current session."
  (interactive)
  (let* ((session-buffer (hdf5-poke--session-buffer))
         (process-buffer (buffer-local-value 'hdf5-poke--process-buffer
                                             session-buffer)))
    (unless (buffer-live-p process-buffer)
      (user-error "No process buffer for this hdf5-poke session"))
    (pop-to-buffer process-buffer)))

;;;###autoload
(defun hdf5-poke-refresh-overview ()
  "Request and render a structured HDF5 file overview."
  (interactive)
  (let ((offset (buffer-local-value 'hdf5-poke--superblock-offset
                                    (hdf5-poke--session-buffer))))
    (hdf5-poke--send-request
     "Overview"
     "hdf5_poke_emacs_superblock"
     offset
     (lambda (records _raws errors)
       (hdf5-poke--render-overview records errors)))))

;;;###autoload
(defun hdf5-poke-set-superblock-offset (offset)
  "Set the HDF5 superblock OFFSET for the current session."
  (interactive (list (hdf5-poke--read-offset "Superblock offset: ")))
  (with-current-buffer (hdf5-poke--session-buffer)
    (setq-local hdf5-poke--superblock-offset offset)
    (setq-local hdf5-poke--object-kind-cache (make-hash-table :test 'equal))
    (setq-local hdf5-poke--path-cache (make-hash-table :test 'equal))
    (let ((inhibit-read-only t))
      (goto-char (point-max))
      (insert "\nSuperblock offset set to " offset "\n"))))

;;;###autoload
(defun hdf5-poke-root-object-header ()
  "Open the root object header's message table."
  (interactive)
  (hdf5-poke-root-object-header-address
   (lambda (offset)
     (hdf5-poke-object-header-messages-at
      offset "/" (list (cons "/" offset))))))

;;;###autoload
(defun hdf5-poke-browse ()
  "Open the root link browser for the current HDF5 file."
  (interactive)
  (hdf5-poke-root-object-header-address
   (lambda (offset)
     (hdf5-poke-links-at offset "/" (list (cons "/" offset))))))

;;;###autoload
(defun hdf5-poke-tree ()
  "Open an expandable HDF5 path tree."
  (interactive)
  (hdf5-poke-root-object-header-address
   (lambda (offset)
     (let* ((session (hdf5-poke--session-buffer))
            (file (buffer-local-value 'hdf5-poke--target-file session))
            (buffer (get-buffer-create (hdf5-poke--tree-buffer-name file)))
            (root (list :name "/"
                        :path "/"
                        :target offset
                        :kind 'group
                        :loaded nil
                        :expanded nil
                        :children nil
                        :stack (list (cons "/" offset)))))
       (with-current-buffer buffer
         (hdf5-poke-tree-mode)
         (setq-local hdf5-poke--origin-session session)
         (setq-local hdf5-poke--tree-root root)
         (hdf5-poke--tree-render))
       (pop-to-buffer buffer)
       (with-current-buffer buffer
         (hdf5-poke--tree-load-children root))))))

;;;###autoload
(defun hdf5-poke-root-object-header-address (&optional callback)
  "Request the root object header address and call CALLBACK with it.

When CALLBACK is nil, display the address in the minibuffer."
  (interactive)
  (let ((offset (buffer-local-value 'hdf5-poke--superblock-offset
                                    (hdf5-poke--session-buffer))))
    (hdf5-poke--send-request
     "Root Object Header Address"
     "hdf5_poke_emacs_root"
     offset
     (lambda (records _raws errors)
       (hdf5-poke--render-errors errors)
       (let* ((root (hdf5-poke--record records 'root))
              (root-offset (plist-get root :offset)))
         (unless root-offset
           (user-error "GNU poke did not return a root object header offset"))
         (if callback
             (funcall callback root-offset)
           (message "Root object header offset: %s" root-offset)))))))

(defun hdf5-poke--resolve-path-link (records name)
  "Return hard-link record named NAME from RECORDS."
  (cl-find-if (lambda (record)
                (and (eq (plist-get record :record) 'link)
                     (equal (plist-get record :name) name)
                     (equal (plist-get record :kind) "hard")
                     (plist-get record :target)))
              records))

(defun hdf5-poke--cache-path-location (path offset stack &optional kind)
  "Cache PATH resolution to OFFSET, STACK, and KIND."
  (let ((location (list :path path :offset offset :stack stack :kind kind)))
    (puthash path location (hdf5-poke--path-cache))
    (when kind
      (hdf5-poke--remember-object-kind offset kind))
    location))

(defun hdf5-poke--resolve-path-components
    (components offset path stack callback)
  "Resolve COMPONENTS below OFFSET and call CALLBACK with the final location."
  (if (null components)
      (funcall callback
               (hdf5-poke--cache-path-location
                path offset stack (hdf5-poke--cached-object-kind offset)))
    (let ((name (car components)))
      (hdf5-poke--send-request
       "Resolve Path Links"
       "hdf5_poke_emacs_links"
       (hdf5-poke--request-args offset)
       (lambda (records _raws errors)
         (hdf5-poke--render-errors errors)
         (let ((link (hdf5-poke--resolve-path-link records name)))
           (unless link
             (user-error "No hard link named %s below %s" name path))
           (let* ((target (plist-get link :target))
                  (child-path (hdf5-poke--child-path path name))
                  (child-stack (append stack (list (cons child-path target)))))
             (hdf5-poke--cache-path-location child-path target child-stack)
             (hdf5-poke--resolve-path-components
              (cdr components) target child-path child-stack callback))))))))

(defun hdf5-poke--resolve-path (path callback)
  "Resolve absolute HDF5 PATH and call CALLBACK with a location plist."
  (let* ((path (hdf5-poke--normalize-path path))
         (cached (gethash path (hdf5-poke--path-cache))))
    (if cached
        (funcall callback cached)
      (hdf5-poke-root-object-header-address
       (lambda (root)
         (hdf5-poke--remember-object-kind root 'group)
         (let ((stack (list (cons "/" root))))
           (if (string= path "/")
               (funcall callback
                        (hdf5-poke--cache-path-location
                         "/" root stack 'group))
             (hdf5-poke--resolve-path-components
              (hdf5-poke--path-components path) root "/" stack callback))))))))

;;;###autoload
(defun hdf5-poke-open-path (path)
  "Open object-header messages for absolute HDF5 PATH."
  (interactive (list (read-string "HDF5 path: " "/")))
  (hdf5-poke--resolve-path
   path
   (lambda (location)
     (hdf5-poke-object-header-messages-at
      (plist-get location :offset)
      (plist-get location :path)
      (plist-get location :stack)))))

;;;###autoload
(defun hdf5-poke-links-path (path)
  "Open links for group at absolute HDF5 PATH."
  (interactive (list (read-string "HDF5 group path: " "/")))
  (hdf5-poke--resolve-path
   path
   (lambda (location)
     (hdf5-poke-links-at
      (plist-get location :offset)
      (plist-get location :path)
      (plist-get location :stack)))))

;;;###autoload
(defun hdf5-poke-preview-path (path &optional max-bytes)
  "Preview dataset at absolute HDF5 PATH."
  (interactive
   (list (read-string "HDF5 dataset path: " "/")
         (read-number "Maximum preview bytes: "
                      hdf5-poke-preview-max-bytes)))
  (hdf5-poke--resolve-path
   path
   (lambda (location)
     (hdf5-poke-preview-dataset-at
      (plist-get location :offset)
      (or max-bytes hdf5-poke-preview-max-bytes)
      (plist-get location :path)))))

;;;###autoload
(defun hdf5-poke-object-header-messages (offset)
  "Decode object header messages at byte OFFSET."
  (interactive (list (hdf5-poke--read-offset-number "Object header offset: ")))
  (hdf5-poke-object-header-messages-at offset))

(defun hdf5-poke-object-header-messages-at (offset &optional path stack)
  "Request and render the object-header message table at OFFSET."
  (hdf5-poke--send-request
   "Object Header Messages"
   "hdf5_poke_emacs_object_header"
   (hdf5-poke--request-args offset)
   (lambda (records _raws errors)
     (hdf5-poke--render-message-list offset records errors path stack))))

;;;###autoload
(defun hdf5-poke-links (offset)
  "List links from the object header at byte OFFSET."
  (interactive (list (hdf5-poke--read-offset-number "Object header offset: ")))
  (hdf5-poke-links-at offset))

(defun hdf5-poke-links-at (offset &optional path stack)
  "Request and render the link table for object header OFFSET."
  (hdf5-poke--send-request
   "Object Header Links"
   "hdf5_poke_emacs_links"
   (hdf5-poke--request-args offset)
   (lambda (records _raws errors)
     (hdf5-poke--render-link-list offset records errors path stack))))

;;;###autoload
(defun hdf5-poke-preview-dataset (offset &optional max-bytes)
  "Preview small compact or contiguous dataset at object-header OFFSET."
  (interactive
   (list (hdf5-poke--read-offset-number "Dataset object-header offset: ")
         (read-number "Maximum preview bytes: "
                      hdf5-poke-preview-max-bytes)))
  (hdf5-poke-preview-dataset-at offset max-bytes))

(defun hdf5-poke-preview-dataset-at (offset &optional max-bytes path)
  "Request a read-only dataset preview at OFFSET.

MAX-BYTES defaults to `hdf5-poke-preview-max-bytes'.  PATH is used for display."
  (let ((max-bytes (or max-bytes hdf5-poke-preview-max-bytes)))
    (hdf5-poke--send-request
     "Dataset Preview"
     "hdf5_poke_emacs_dataset_preview"
     (hdf5-poke--request-args offset (format "%dUL" max-bytes))
     (lambda (records _raws errors)
       (hdf5-poke--render-dataset-preview offset records errors path)))))

;;;###autoload
(defun hdf5-poke-chunk-index (offset &optional ndims)
  "Decode the chunk index at byte OFFSET.

NDIMS is only required for version 1 chunk B-trees, where the key shape is
not self describing.  Layout action buttons pass it automatically."
  (interactive
   (list (hdf5-poke--read-offset-number "Chunk index offset: ")
         (read-number "Chunk dimensions for v1 B-tree (0 for unknown): " 0)))
  (hdf5-poke-chunk-index-at offset ndims))

(defun hdf5-poke-chunk-index-at (offset &optional ndims dims)
  "Request and render a chunk-index table at OFFSET.

NDIMS may be nil or zero for self-describing chunk index implementations.
DIMS is the chunk dimension list from the layout message, when available."
  (let ((ndims (or ndims 0)))
    (hdf5-poke--send-request
     "Chunk Index"
     "hdf5_poke_emacs_chunk_index"
     (hdf5-poke--request-args offset (format "%dUB" ndims))
     (lambda (records _raws errors)
       (hdf5-poke--render-chunk-index offset ndims records errors dims)))))

;;;###autoload
(defun hdf5-poke-v1-btree (offset)
  "Inspect a version 1 B-tree node at byte OFFSET."
  (interactive (list (hdf5-poke--read-offset-number "Version 1 B-tree offset: ")))
  (hdf5-poke-raw-at "v1-btree" offset))

;;;###autoload
(defun hdf5-poke-set-v1-btree-ndims (ndims)
  "Set the v1 raw chunk B-tree key dimensionality to NDIMS."
  (interactive "nB-tree ndims value: ")
  (unless (natnump ndims)
    (user-error "ndims must be non-negative"))
  (hdf5-poke--send "Set v1 B-tree ndims"
                   (format "set_bt1_ndims (%dUB)" ndims)))

;;;###autoload
(defun hdf5-poke-pretty-print (kind offset &optional size)
  "Pretty-print KIND at byte OFFSET using protocol-delimited raw output."
  (interactive
   (let* ((kind (completing-read "Kind: "
                                 '("superblock" "object-header" "v1-btree" "bytes")
                                 nil t nil nil "object-header"))
          (offset (hdf5-poke--read-offset-number "Offset: "))
          (size (and (string= kind "bytes")
                     (read-number "Byte count: " 64))))
     (list kind offset size)))
  (hdf5-poke-raw-at kind offset size))

(defun hdf5-poke-raw-at (kind offset &optional size)
  "Request raw pretty output for KIND at OFFSET.

SIZE is used only when KIND is \"bytes\"."
  (hdf5-poke--send-request
   "Raw Pretty Print"
   "hdf5_poke_emacs_raw"
   (hdf5-poke--join-args
    (hdf5-poke--poke-string kind)
    (hdf5-poke--offset-expression offset)
    (format "%dUL" (or size 0))
    (hdf5-poke--superblock-offset-expression))
   (lambda (_records raws errors)
     (hdf5-poke--render-raw kind offset raws errors))))

(defun hdf5-poke-revert-object-header-messages ()
  "Refresh the current object-header message table."
  (interactive)
  (unless hdf5-poke--object-header-offset
    (user-error "This buffer is not associated with an object header"))
  (hdf5-poke-object-header-messages-at hdf5-poke--object-header-offset
                                       hdf5-poke--object-path
                                       hdf5-poke--path-stack))

(defun hdf5-poke-message-list-open ()
  "Open a raw detail view for the selected object-header message."
  (interactive)
  (let ((record (tabulated-list-get-id)))
    (unless (and (listp record)
                 (eq (plist-get record :record) 'message))
      (user-error "No message row at point"))
    (hdf5-poke-message-detail-at
     (plist-get record :type)
     (plist-get record :payload-offset)
     (plist-get record :size)
     (plist-get record :name))))

(defun hdf5-poke-message-detail-at (type payload-offset size &optional name)
  "Request and render a raw detail view for a message payload."
  (hdf5-poke--send-request
   "Message Detail"
   "hdf5_poke_emacs_message"
   (hdf5-poke--join-args
    (format "%dUB" type)
    (hdf5-poke--offset-expression payload-offset)
    (format "%dUH" size)
    (hdf5-poke--superblock-offset-expression))
   (lambda (records raws errors)
     (hdf5-poke--render-message-detail
      type payload-offset records raws errors name))))

(defun hdf5-poke-links-for-current-object-header ()
  "Open links for the object header represented by the current buffer."
  (interactive)
  (unless hdf5-poke--object-header-offset
    (user-error "This buffer is not associated with an object header"))
  (hdf5-poke-links-at hdf5-poke--object-header-offset
                      hdf5-poke--object-path
                      hdf5-poke--path-stack))

(defun hdf5-poke-preview-current-object-header ()
  "Preview the current object header as a small dataset."
  (interactive)
  (unless hdf5-poke--object-header-offset
    (user-error "This buffer is not associated with an object header"))
  (hdf5-poke-preview-dataset-at hdf5-poke--object-header-offset
                                hdf5-poke-preview-max-bytes
                                hdf5-poke--object-path))

(defun hdf5-poke-link-list-open ()
  "Open the selected hard-link target in the path browser."
  (interactive)
  (let ((record (tabulated-list-get-id)))
    (unless (and (listp record)
                 (eq (plist-get record :record) 'link))
      (user-error "No link row at point"))
    (unless (string= (plist-get record :kind) "hard")
      (user-error "Only hard-link rows can be opened"))
    (let* ((target (plist-get record :target))
           (name (plist-get record :name))
           (path (hdf5-poke--child-path hdf5-poke--object-path name))
           (stack (append (or hdf5-poke--path-stack
                              (list (cons (or hdf5-poke--object-path "/")
                                          hdf5-poke--object-header-offset)))
                          (list (cons path target)))))
      (unless target
        (user-error "Selected link has no target object header"))
      (hdf5-poke-links-at target path stack))))

(defun hdf5-poke-revert-links ()
  "Refresh the current object-header link table."
  (interactive)
  (hdf5-poke-links-for-current-object-header))

(defun hdf5-poke-revert-chunk-index ()
  "Refresh the current chunk-index table."
  (interactive)
  (unless hdf5-poke--chunk-index-offset
    (user-error "This buffer is not associated with a chunk index"))
  (hdf5-poke-chunk-index-at hdf5-poke--chunk-index-offset
                            hdf5-poke--chunk-index-ndims
                            hdf5-poke--chunk-index-dims))

(defun hdf5-poke-chunk-list-open ()
  "Open the selected chunk's raw bytes."
  (interactive)
  (let ((record (tabulated-list-get-id)))
    (unless (and (listp record)
                 (eq (plist-get record :record) 'chunk))
      (user-error "No chunk row at point"))
    (let ((addr (plist-get record :chunk-addr))
          (size (or (plist-get record :chunk-size) 64)))
      (unless addr
        (user-error "Selected chunk has no file address"))
      (hdf5-poke-raw-at "bytes" addr size))))

(defun hdf5-poke-pretty-print-current-chunk-index ()
  "Pretty-print the current chunk-index metadata when possible."
  (interactive)
  (unless hdf5-poke--chunk-index-offset
    (user-error "This buffer is not associated with a chunk index"))
  (let ((kind (plist-get hdf5-poke--chunk-index-record :kind)))
    (if (string= kind "v1-btree")
        (hdf5-poke-raw-at "v1-btree" hdf5-poke--chunk-index-offset)
      (hdf5-poke-raw-at "bytes" hdf5-poke--chunk-index-offset 256))))

(defun hdf5-poke-object-header-messages-for-current-links ()
  "Open messages for the object header represented by a link table."
  (interactive)
  (hdf5-poke-revert-object-header-messages))

(defun hdf5-poke-pretty-print-current-object-header ()
  "Pretty-print the object header represented by the current buffer."
  (interactive)
  (unless hdf5-poke--object-header-offset
    (user-error "This buffer is not associated with an object header"))
  (hdf5-poke-raw-at "object-header" hdf5-poke--object-header-offset))

;;;###autoload
(defun hdf5-poke-load-pickle (module)
  "Load an additional pickle MODULE into the current GNU poke process."
  (interactive "sPickle module name: ")
  (when (string-match-p "[[:space:]\n\r]" module)
    (user-error "Module names must not contain whitespace"))
  (hdf5-poke--send "Load Pickle" (format "load %s" module)))

;;;###autoload
(defun hdf5-poke-eval (source)
  "Send raw poke SOURCE to the current session."
  (interactive "sPoke expression or statement: ")
  (hdf5-poke--send "Raw Eval" source))

;;;###autoload
(defun hdf5-poke-write-expression (source)
  "Send raw write SOURCE to GNU poke after confirmation.

This command is intentionally generic for the scaffold.  Set
`hdf5-poke-enable-writes' before using it."
  (interactive "sPoke write expression: ")
  (unless hdf5-poke-enable-writes
    (user-error "Set hdf5-poke-enable-writes before sending write expressions"))
  (unless (y-or-n-p "Send low-level write expression to GNU poke? ")
    (user-error "Canceled"))
  (hdf5-poke--send "Raw Write" source))


(provide 'hdf5-poke-ui)

;;; hdf5-poke-ui.el ends here
