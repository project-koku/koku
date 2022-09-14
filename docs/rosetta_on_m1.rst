Using Rosetta
=============

Rosetta enables a Mac with Apple silicon to use apps built for a Mac with an Intel processer. Follow the steps on `how to install Rosetta on your Mac`_.

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

2. Installing ``brew``
----------------------

We also will want to have a separate ``brew`` version that runs Intel-based programs. When you install Homebrew on an Intel Mac, it installs it in the `/usr/local/homebrew` directory.

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

1. Install Python 3.9 using Intel-based ``brew``: ::

    brow install python@3.9
    brow list | grep python

2. Assuming ``python`` and ``pip`` (comes with ``python`` installation above) currently do not point to any commands, add the following paths and aliases to ``~/.zshrc``: ::

    export PATH="/usr/local/homebrew/Cellar/python@3.9/3.9.13_1/bin/python3.9:$PATH"
    export PATH="/usr/local/homebrew/Cellar/python@3.9/3.9.13_1/bin/pip3:$PATH"

    alias python='/usr/local/homebrew/Cellar/python@3.9/3.9.13_1/bin/python3.9'
    alias pip='/usr/local/homebrew/Cellar/python@3.9/3.9.13_1/bin/pip3'

3. Implement the new changes in ``.zshrc`` file: ::

    source ~/.zshrc


References
----------

- https://medium.com/mkdir-awesome/how-to-install-x86-64-homebrew-packages-on-apple-m1-macbook-54ba295230f
- https://til.simonwillison.net/macos/running-docker-on-remote-m1


.. _`iTerm2`: https://iterm2.com/
.. _`how to install Rosetta on your Mac`: https://support.apple.com/en-us/HT211861
