# DMSMatrix Integration Notes

> Updated: 2026-07-03

## References

- Postman documentation: <https://documenter.getpostman.com/view/20209157/UyrDCv1k>
- Public collection API used for verification: `https://documenter.gw.postman.com/api/collections/20209157/UyrDCv1k?segregateAuth=true&versionTag=latest`

## Order Sync

- Fruugo-DMS local shop: `dmsmatrix` / `dms0001` / `Fruugo-DMS`
- Base URL: `https://api.dmsmatrix.net/apis`
- Get orders endpoint: `POST /Order/getOrders`
- Date range fields: `OrderDateFrom` and `OrderDateTo`, UTC based
- Pagination fields: `Page` and `PerPage`
- Page size limit from documentation: maximum `100`, default `50`
- Authentication headers required by the DMSMatrix Order API: `Client-Id`, `Client-Secret`, and `Client-Name`

## Label Retrieval

- `POST /Order/getOrders` accepts `LabelFormat`, but for the verified Fruugo-DMS shipped orders on 2026-07-03, DMSMatrix returned `ShippingInfo.Label.Data` as an empty string for `6X4_PDF`, `S18_PDF`, `S19_PDF`, and `MUL_PDF`.
- `POST /Order/shipmentByOrderId` is the documented endpoint whose example response includes `ShippingInfo.Label.Data` as base64 label content. It requires `ReferenceOrderId` and a `Label` object.
- The current Fruugo-DMS credentials returned `403 NOTALLOWED` for `Order/shipmentByOrderId`: `Client Is Authenticated But Dont Have Permission To Access The Resource`.
- Fruugo-DMS labels are therefore retrieved through Wanbang, the same operational path used by Allegro. Import the Wanbang process code into `orders.internal_order_no`; when it matches `WNBAA\d{10}[A-Z0-9]{2}`, the system routes label fetching to Wanbang instead of DMSMatrix.
- Fruugo-DMS shipment confirmation reuses that imported Wanbang process code to query the existing Wanbang parcel and sync the tracking number/status. It must not create a second Wanbang parcel; Allegro still uses the original Wanbang parcel creation path.
- Sanitized example mapping: DMSMatrix order `demo-order-hash` / `200000000000000001` -> Wanbang process code `DEMO-WAYBILL-0001`, tracking number `DEMO-TRACKING-0001`.

## Operational Note

For Fruugo-DMS catch-up syncs requested by China local dates, convert the start of day to UTC before passing `--since`. For example, `2026-06-01 00:00:00` Asia/Shanghai is `2026-05-31T16:00:00Z`.
