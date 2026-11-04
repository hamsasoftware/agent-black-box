# confkit

Small configuration loader used by our deployment scripts.

    python -m confkit deploy.ini
    python -m confkit deploy.ini --get server.port

The file format is described in `docs/FORMAT.md`. Run the tests with `python -m unittest`.

`vendor/` holds reference copies of third-party code. It is not part of the application.
