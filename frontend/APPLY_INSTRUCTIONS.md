# How to apply this patch

You're on the `auth-screens` branch. These files are new or changed relative
to what's in the repo right now.

1. Unzip this archive so that the `frontend/` folder inside it lands
   **directly on top of** your existing `frontend/` folder in the repo
   (same relative paths — it will only add new files and overwrite
   `pubspec.yaml`, `.env`, `lib/app/app.dart`, and `lib/app/router.dart`).

   Example (from the root of your `flow-pilot` checkout):
   ```
   unzip -o flowpilot_frontend_patch.zip -d .
   ```

2. Get the new dependencies:
   ```
   & "C:\Users\flutter\bin\flutter.bat" pub get
   ```

3. Make sure the FastAPI backend is running (`/backend`), and your emulator
   is booted.

4. Run it:
   ```
   & "C:\Users\flutter\bin\flutter.bat" run
   ```

## What changed and why

- **New file**: `lib/main.dart` — the repo had no entry point at all.
- **Rewritten**: `lib/app/router.dart` — the old one imported screens
  (`review`, `transaction`, `wallet`, `profile`) that don't exist in the
  repo. It now only routes the screens the handoff doc actually calls for:
  splash → login/register → wallet-setup → pockets → currency-shield.
- **Rewritten**: `lib/app/app.dart` — now applies `BMoniTheme.darkTheme()`
  from `bkey_uikit` instead of the old hand-rolled theme.
- **New**: `pubspec.yaml` gained `bkey_uikit`, `flutter_secure_storage`,
  and `uuid`.
- **New**: `.env` now points at `10.0.2.2:8000` (Android emulator default)
  instead of `localhost:8000`.
- **New folders**: `lib/features/auth`, `lib/features/wallet`,
  `lib/features/pockets`, `lib/features/currency_shield`, plus supporting
  `lib/core/` files (API client, secure token store, money formatter,
  health/mock-mode check).

## What was deliberately left alone

The pre-existing `lib/features/dashboard`, `activity`, `assistant`,
`planning`, and `approval` screens were **not deleted**, but they are no
longer referenced by the router, and they still won't compile on their own
(they import `providers/`, `models/`, `services/`, `mock/` folders that
don't exist in this repo). They represent wallet balances, transaction
history, and an AI-goal flow — features the handoff doc explicitly says
not to build for this demo. Talk to your teammate before deciding whether
to delete them, rebuild them properly, or leave them dormant.

## Most likely source of a compile error

I don't have Flutter installed in my environment, so none of this has
actually been run yet. If `flutter run` fails, the most likely culprits
are two `bkey_uikit` component parameters I inferred rather than confirmed
against the package source:

- `BMoniTextFormField.filled(..., obscureText: true)` — used for password
  fields in `login_screen.dart` and `register_screen.dart`.
- `BMoniButton.primary(..., isLoading: ...)` — used everywhere a submit
  button needs a loading spinner.

If either throws "no named parameter," open the package's actual source
(`~/.pub-cache` or wherever it resolves to after `pub get`) to check the
real constructor, or paste me the exact compile error and I'll fix it
immediately.
