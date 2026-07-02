;;; hdf5-poke.el --- Inspect HDF5 files with GNU poke pickles -*- lexical-binding: t; -*-

;; Copyright (C) 2026 The HDF Group.

;; Author: HDF Group
;; Keywords: data, files, tools
;; Package-Requires: ((emacs "30.1"))
;; SPDX-License-Identifier: GPL-3.0-or-later

;; This program is free software: you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation, either version 3 of the License, or
;; (at your option) any later version.

;;; Commentary:

;; This is an Emacs front-end for the GNU poke HDF5 pickles in this repository.
;; It intentionally talks to GNU poke directly instead of using the h5explain
;; shell wrapper.
;;
;; Start with:
;;
;;   M-x hdf5-poke-open-file

;;; Code:

(eval-and-compile
  (let ((directory (file-name-directory
                    (or load-file-name buffer-file-name default-directory))))
    (when directory
      (add-to-list 'load-path directory))))

(require 'hdf5-poke-ui)

(provide 'hdf5-poke)

;;; hdf5-poke.el ends here
