# Rung 4: PhiOperator public PhiOS site pilot

This is an **optional static web page** at /PhiOS/operator-passport/.
It is **not** integrated with native PhiOS Linux authorization, app
installation, runtime identity, action leases, offline boot, or release gates.

The canonical SDK is PhiOperator src/portable-passport.js pinned to commit
402aa3b161737926617d578370749826e3fda97a. The local offline ESM copy is site/public/operator-passport/sdk.js.
Vite copies the entire static station into site/dist without fetching runtime code.

From PhiOperator export v1 JSON. Select it manually using the station's file
picker and confirm import. A sequential Standard Rank 3 reveals a decorative
Field Grid; Standard Rank 6 adds an Architect seal. The public site functions
fully without any Passport. It can export and forget its local copy.

JSON is editable game progress, never authentication, credentials, trust or
security authority. The module does no cross-origin calls, no sync and no
authorization. No changes to system administration are permitted in this rung.

Verify with site unit tests and the regular site build, static deployment,
and browser smoke of the station. Native PhiOS release qualification remains
a separate process.