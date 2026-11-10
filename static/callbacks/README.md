# Static sandbox callback destinations

These two standalone pages are the Cart Consent demonstration's browser destinations:

- Return: https://misakamikotoghr-5205.github.io/cart-consent-paypal/return.html
- Cancel: https://misakamikotoghr-5205.github.io/cart-consent-paypal/cancel.html

Both were verified anonymously over HTTPS on 2026-11-10: HTTP 200, `text/html; charset=utf-8`, and byte-for-byte equality with the source HTML. The official Pages build reported `built` with no error.

The pages contain inline CSS and text only: no script, URL-query reader, API call, form, payment button or external resource. Their content security policy defaults to blocking resources and permits only inline styling. Neither returning nor visiting the cancellation page proves payment, approval, capture, cancellation, refund or delivery status. The local service must verify its own order state; these pages perform no payment operation.

## Publication configuration

GitHub Pages publishes the independent `gh-pages` branch, path `/`, with HTTPS enforced and `build_type=legacy`. The published branch contains exactly:

```text
.nojekyll
cancel.html
return.html
```

The HTML is copied from this folder; `.nojekyll` is empty. Only this explicit allowlist is published. The Python server, repository documentation, environment configuration and private ledgers are not part of the Pages tree. The site root has no directory index.

To update the callbacks, review the two HTML files, publish only those files and the empty `.nojekyll` to `gh-pages`, then verify both HTTPS responses against their source bytes. Do not publish the Python repository root. No custom Actions workflow or extra dependency is required for this branch publication; GitHub provides its Pages deployment workflow.

Official references: [GitHub Pages branch publishing](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) and [Pages REST configuration](https://docs.github.com/en/rest/pages/pages).
