# Submodules

At time of writing, Thread uses one submodule. To set this up, please do the following within the project's directory:

- one-time command on setup

```
git submodule init
```

- a command you will use periodically for updates

```
git submodule update --remote
```

- optional last step to see if the project-hash matches the latest commit-hash in the dependency project's repository

```
git submodule status
```
