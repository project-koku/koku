# Koku Development Documentation

## Debugging Celery Workers and Remote Attach with VSCode

### Celery Worker Auto-Reload Issue

One of the issues we've encountered in our development workflow is related to Celery workers not auto-reloading with Rancher. This can be inconvenient as it requires manual intervention to reload the worker when making changes.

**Issue:** The Celery worker does not auto-reload with Rancher, leading to development challenges.

**Solution:** We need to address this issue to streamline our development process.

### Remote Attach Debugging with Visual Studio Code (VSCode)

Debugging Celery workers in Koku can be made more efficient by setting up remote debugging with VSCode. Here are the steps to enable remote debugging:

1. **Start with a clean database.** Ensure that you have a fresh database to work with.

2. **VSCode Configuration:**
   - Create a `launch.json` configuration in VSCode with the following content:

   ```json
   {
       "name": "Python: Celery Attach",
       "type": "python",
       "request": "attach",
       "port": 5678,
       "host": "localhost",
       "pathMappings": [
           {
               "localRoot": "${workspaceFolder}/koku",
               "remoteRoot": "."
           }
       ]
   }

More info can be found here: https://github.com/project-koku/koku/pull/4732
