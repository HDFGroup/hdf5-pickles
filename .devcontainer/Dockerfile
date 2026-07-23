FROM archlinux:base-devel

LABEL org.opencontainers.image.title="H5Lens development environment" \
      org.opencontainers.image.description="GNU poke, HDF5, Python, Emacs, and native-analysis tooling for H5Lens"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Keep the development and analysis stack in the image. A Codespace should not
# need a rolling system upgrade before the repository can build or run.
RUN pacman -Syu --noconfirm --needed \
        bash-completion \
        ca-certificates \
        cmake \
        curl \
        emacs-nox \
        gdb \
        git \
        github-cli \
        hdf5 \
        jq \
        less \
        libaec \
        libasan \
        man-db \
        openssh \
        poke \
        procps-ng \
        python \
        python-h5py \
        python-numpy \
        python-pip \
        python-yaml \
        ripgrep \
        rsync \
        shellcheck \
        sudo \
        time \
        unzip \
        vim \
        which \
        zlib \
    && pacman -Scc --noconfirm

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000
ARG HDF5_REPOSITORY=https://github.com/HDFGroup/hdf5.git

ENV HDF5_SOURCE_DIR=/opt/hdf5 \
    HDF5_ASAN_PREFIX=/opt/hdf5-asan

RUN groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd \
        --uid "${USER_UID}" \
        --gid "${USER_GID}" \
        --create-home \
        --shell /bin/bash \
        "${USERNAME}" \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" \
        >"/etc/sudoers.d/90-${USERNAME}" \
    && chmod 0440 "/etc/sudoers.d/90-${USERNAME}" \
    && install -d -o "${USERNAME}" -g "${USERNAME}" \
        /opt/hdf5 \
        /opt/hdf5-asan \
        /workspaces

USER ${USERNAME}
WORKDIR /workspaces

# Keep the complete upstream history available for bisecting, archaeology, and
# CVE analysis. This is intentionally an image-build step, not a post-create
# network dependency.
RUN git clone \
        "${HDF5_REPOSITORY}" \
        "${HDF5_SOURCE_DIR}"
