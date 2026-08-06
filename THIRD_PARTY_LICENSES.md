# Third-Party Dependency Licenses

CaifuClaw AI is distributed under the Apache License 2.0, but its dependencies
remain under their own licenses. Dependency packages are installed from their
package registries and are not relicensed by this repository.

The reviewed production frontend dependency tree contains MIT, ISC,
Apache-2.0, BSD-3-Clause, 0BSD, and Unlicense packages. `wouter`, the frontend
router, uses the Unlicense.

The reviewed direct Python dependencies use permissive licenses except
`psycopg`, which uses the GNU Lesser General Public License v3. The project uses
`psycopg` as an independently installed PostgreSQL client library and does not
modify or vendor its source.

Package metadata and license texts installed with each dependency are the
authoritative records. Re-run the local summaries with:

```powershell
Push-Location caifuclaw_business_app\frontend
npx --yes license-checker@25.0.1 --production --summary
Pop-Location

python -m pip install pip-licenses
python -m piplicenses --summary
```

Review this file and the generated summaries whenever dependencies change.
