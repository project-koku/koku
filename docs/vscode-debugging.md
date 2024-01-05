# (Visual Studio Code) VSCode Debugging

## Debugging Celery Workers and Remote Attach in VSCode

Debugging Celery workers in Koku can be made more efficient by setting up remote debugging with VSCode. Here are the steps to enable remote debugging:

1. **Update environment variables.** Set `DEBUG_ATTACH=True` and reload the `.env` file.

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

3. Start the `koku-worker` with the updated `.env` variables.

4. Observe the worker logs and wait for the message:
   ```
   koku-koku-worker-1  | Waiting for debugger attach on port 5678
   ```

5. In VSCode, in the *Run and Debug* view, select the `Python: Celery Attach` configuration and start the debug session.

6. Once the debugger attaches to the container, the worker will resume starting like normal.

7. Set breakpoints and debug away!

**Note:** If code changes are made, the container will auto-reload and the debugger will detach! It is necessary to re-attach the debugger to continue debugging.

More info can be found here: https://github.com/project-koku/koku/pull/4732
