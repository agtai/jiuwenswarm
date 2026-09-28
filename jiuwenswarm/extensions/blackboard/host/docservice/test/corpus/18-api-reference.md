# Edits endpoint

`POST /api/docs/:id/edits` applies a batch of block operations.

## Request

```json
{
  "mandateId": "m_01J9",
  "ops": [{ "op": "replace", "blockId": "b3", "digest": "9f2c", "markdown": "New text." }]
}
```

## Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `mandateId` | string | yes | the running mandate |
| `ops` | array | yes | 1 to 50 operations |
| `note` | string | no | shown next to the suggestions |

## Errors

- `stale`: a touched block changed since it was read.
- `out_of_scope`: a block lies outside the mandate scope.
- `unknown_block`: the block id does not exist.

## Example

```sh
curl -X POST http://127.0.0.1:19010/api/docs/d1/edits \
  -H "X-BB-Secret: $SECRET" \
  -d @batch.json
```
