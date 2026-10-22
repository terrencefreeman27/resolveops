# Single Sign-On and Account Access

## SAML SSO

SAML SSO is available on Business and Enterprise plans. An Admin configures it in
**Settings → Security → Single sign-on** with the identity provider's metadata URL. Once
"Enforce SSO" is enabled, password sign-in is disabled for everyone except one designated
break-glass Admin.

## SCIM provisioning

Enterprise accounts can provision and deprovision users with SCIM. Roles assigned through SCIM
group mappings override roles set manually.

## Password resets and lockouts

Users reset passwords from the sign-in page. Five failed sign-in attempts lock an account for
15 minutes. Support cannot reveal or set passwords.

## Access a user should not have

If a customer reports that someone has access they should not, advise the Admin to deactivate the
user in **Settings → Users & Roles** and escalate as a security concern (see "Escalation Policy").
