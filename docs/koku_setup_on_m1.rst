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

3. Add the following path and alias to the ``.zshrc`` file. *Note*: We are setting an alias ``brow`` (you could name it anything you'd like) to the version of ``homebrew`` that run on Intel-based machines. ::

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

Alternatively, if you want to run the project in Docker environment, follow the below steps:

1. Set ``compose_file`` in your ``.env`` file to point to docker-compose-m1.yml_ file specially created for M1 Mac: ::

    compose_file='testing/compose_files/docker-compose-m1.yml'

2. docker-compose-m1.yml_ removes the use of ``watchdog`` package as at the time of creating this documentation, `watchdog` package is not supported on M1.
   Instead, we use a VSCode extension to run a `bash script`_ on Save in order to re-build docker containers.
   From VSCode Extensions, install `emeraldwalk.RunOnSave` and add the following to `settings.json`. More on `Run on Save`_: ::

    {
        ...
        "emeraldwalk.runonsave": {
            "commands": [
                {
                    "cmd": "bash <path-to-project>/koku/dev/scripts/m1_refresher.sh"
                }
            ]
        }
    }


References
----------
- https://medium.com/mkdir-awesome/how-to-install-x86-64-homebrew-packages-on-apple-m1-macbook-54ba295230f
- https://til.simonwillison.net/macos/running-docker-on-remote-m1
- https://github.com/jsbroks/coco-annotator/issues/493

.. _`how to install Rosetta on your Mac`: https://support.apple.com/en-us/HT211861
.. _`iTerm2`: https://iterm2.com/
.. _`Koku's original development`: https://github.com/project-koku/koku/blob/main/README.rst#development
.. _`Koku's README`: https://github.com/project-koku/koku/blob/main/README.rst
.. _`docker-compose-m1.yml`: https://github.com/project-koku/koku/blob/main/testing/compose_files/docker-compose-m1.yml
.. _`Run on Save`: https://betterprogramming.pub/automatically-execute-bash-commands-on-save-in-vs-code-7a3100449f63
.. _`bash script`: https://github.com/project-koku/koku/tree/main/dev/scripts/m1_refresher.sh
