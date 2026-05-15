# (Visual Studio Code) VSCode Debugging

## Debugging Celery Workers and Remote Attach in VSCode

Debugging Celery workers in Koku can be made more efficient by setting up remote debugging with VSCode.

### Single Worker Debugging (Default)

1. **Update environment variables.** Set `DEBUG_ATTACH=True` in your `.env` file.

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
   ```

3. **Start the koku-worker:**
   ```bash
   make docker-up-min-trino-no-build
   # This starts 1 worker by default (scale=1) with debug port 5678 exposed
   ```

4. Observe the worker logs and wait for the message:
   ```
   koku-worker-1  | Waiting for debugger attach on port 5678
   ```

5. In VSCode, in the *Run and Debug* view, select the `Python: Celery Attach` configuration and start the debug session.

6. Once the debugger attaches to the container, the worker will resume starting like normal.

7. Set breakpoints and debug away!

### Notes:

* If code changes are made, the container will auto-reload and the debugger will detach! It is necessary to re-attach the debugger to continue debugging. More info can be found here: https://github.com/project-koku/koku/pull/4732


* Remote debugging only works with a single worker (`scale=1`, the default).

### Troubleshooting

* No debug attach: Verify `DEBUG_ATTACH=True` is in your `.env` file and you're using `scale=1` (default)
* Port already in use: Ensure no other process is using port 5678: `lsof -i :5678`
* Trino connection errors: The Makefile ensures Trino is fully started before workers connect. If issues persist:
  ```bash
  docker restart trino
  make docker-logs
  ```
