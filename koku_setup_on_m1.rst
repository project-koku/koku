=====================
Koku Setup on M1 Mac
=====================

About
=====

This documentation is to guide M1 Mac users on how to successfully install and run Koku on their machines.

Getting Started
================

This guide mostly makes use of Rosetta in order to get Intel-based programs and packages to run on Mac with Apple silicon processors (M1).

Using Rosetta (2)
-----------------

Rosetta 2 enables a Mac with Apple silicon to use apps built for a Mac with an Intel processer. Check out and follow the steps on `how to install Rosetta on your Mac`_.

TL;DR: ::

    /usr/sbin/softwareupdate --install-rosetta --aggree-to-license

1. Running Terminal with Rosetta
--------------------------------

It is a good idea to have a separate terminal to run with Rosetta, while keeping the default terminal run on M1.

1. Download and install `iTerm2`_
2. Go to Applications in Finder
3. Find iTerm, right-click and select `Get Info`
4. Make sure `Open using Rosetta` is checked

Alternatively, you can create a copy of your default terminal, rename the copy and have it run specifically with Rosetta.

`Note`: We will be using this version of the terminal for all the steps that follow.

1. Installing ``brew``
----------------------

Same as we have a separate terminal running Intel-based programs, we also want to have a separate ``brew`` version that run Intel-based programs. When you install Homebrew on an Intel Mac, it installs it in the `/usr/local/homebrew` directory.

1. Create a ``~/Downloads/homebrew`` and download Homebrew tarball and extract it to the ``~/Downloads/homebrew`` directory: ::

    cd ~/Downloads
    mkdir homebrew
    curl -L https://github.com/Homebrew/brew/tarball/master | tar xz --strip 1 -C homebrew

2. Move the ``homebrew`` directory to ``/usr/local/homebrew``. You need the ``sudo`` command: ::

    sudo mv homebrew /usr/local/homebrew

3. Add the following path and alias to the ``.zshrc`` file: ::

    # need this for x86_64 brew
    export PATH=$HOME/bin:/usr/local/bin:$PATH
    export PATH="/usr/local/homebrew/bin:$PATH"

    # for intel x86_64 brew
    alias brow='arch -x86_64 /usr/local/homebrew/bin/brew'

4. Implement the new changes in ``.zshrc`` file: ::

    source ~/.zshrc

Now you can install apps for Intel processors: ::

    brow install package-name

And you can use all ``brew`` commands: ::

    brow list
    brow reinstall package-name
    brow --help

3. Install Python
-----------------

1. Install Python 3.8 using Intel-based ``brew``: ::

    brow install python@3.8
    brow list | grep python

2. Assuming ``python`` and ``pip`` (comes with ``python`` installation above) currently do not point to any commands, add the following paths and aliases to ``~/.zshrc``: ::

    export PATH="/usr/local/homebrew/Cellar/python@3.8/3.8.13/bin/python3.8:$PATH"
    export PATH="/usr/local/homebrew/Cellar/python@3.8/3.8.13/bin/pip3:$PATH"

    alias python='/usr/local/homebrew/Cellar/python@3.8/3.8.13/bin/python3.8'
    alias pip='/usr/local/homebrew/Cellar/python@3.8/3.8.13/bin/pip3'

3. Implement the new changes in ``.zshrc`` file: ::

    source ~/.zshrc

4. Development
--------------

At this point, you should be able to follow the steps in `Koku's original development`_ process from `1` through `9`; just make sure you use ``brow`` instead of ``brew`` and ``pip`` instead of ``pip3`` in order to use the versions that we installed above.

Developing with Docker
^^^^^^^^^^^^^^^^^^^^^^

Alternatively, if you want to run the project in Docker environment, you can follow the same process in `Koku's README`_ only with the following changes in `docker-compose.yml`_ file:

1. Under ``koku-base`` service, specify the ``platform`` that the container should be built on: ::

    ..
    services:
        koku-base:
            image: koku_base
            platform: linux/amd64
    ..

2. In the ``entrypoints`` list under ``koku-worker`` service, remove the items starting from ``watchdog`` up until ``celery`` (NOT including ``celery``). At the time of creating this documentation, ``watchdog`` package is not supported on M1: ::

    ..
    koku-worker:
        hostname: koku-worker-1
        image: koku_base
        working_dir: /koku/koku
        entrypoint: ['watchmedo', 'auto-restart', .., 'celery', '-A' ..]
    ..

References
----------
- https://medium.com/mkdir-awesome/how-to-install-x86-64-homebrew-packages-on-apple-m1-macbook-54ba295230f
- https://til.simonwillison.net/macos/running-docker-on-remote-m1
- https://github.com/jsbroks/coco-annotator/issues/493

.. _`how to install Rosetta on your Mac`: https://support.apple.com/en-us/HT211861
.. _`iTerm2`: https://iterm2.com/
.. _`Koku's original development`: https://github.com/project-koku/koku/blob/main/README.rst#development
.. _`Koku's README`: https://github.com/project-koku/koku/blob/main/README.rst
.. _`docker-compose.yml`: https://github.com/project-koku/koku/blob/main/docker-compose.yml
