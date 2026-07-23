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
        unzip \
        vim \
        which \
    && pacman -Scc --noconfirm

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

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
    && install -d -o "${USERNAME}" -g "${USERNAME}" /workspaces

USER ${USERNAME}
WORKDIR /workspaces
