# Serverless Resume API on AWS

A serverless REST API that serves resume data, built with **API Gateway**, **Lambda (Python 3.12)** and **DynamoDB**, deployed with **AWS SAM**. Access requires an **API key**, and a **usage plan** enforces throttling and a daily quota.

## Architecture

```
Client ──(x-api-key)──> API Gateway ──> Lambda (handler.py) ──> DynamoDB
                         │ usage plan                              ▲
                         │ (rate/burst/quota)                      │ seeded from
                         ▼                                         │ src/resume.json
                    401/403/429 when                      Custom-resource Lambda (seed.py)
                    key missing or limit hit
```

## Endpoints

| Method | Path          | Returns                                     |
|--------|---------------|---------------------------------------------|
| GET    | `/personal`   | Name, title, contact details, summary, links |
| GET    | `/experience` | Work experience (most recent first)          |
| GET    | `/education`  | Education history                            |
| GET    | `/skills`     | Skills grouped by category                   |
| GET    | `/resume`     | All of the above in one response             |

Every request needs the header `x-api-key: <your key>`.

## DynamoDB design

| Attribute | Role           | Example                                  |
|-----------|----------------|------------------------------------------|
| `section` | Partition key  | `personal`, `experience`, `education`, `skills` |
| `itemId`  | Sort key       | `profile`, `001`, `002`, ...             |

One query per section returns its items already ordered by the sort key. The table uses on-demand billing, encryption at rest and point-in-time recovery.

## Project structure

```
.
├── template.yaml          # SAM/CloudFormation: table, API, key, usage plan, Lambdas
├── samconfig.toml         # Default deploy settings
├── src/
│   ├── handler.py         # API Lambda (reads DynamoDB, falls back to resume.json)
│   ├── seed.py            # Custom-resource Lambda that loads resume.json into DynamoDB
│   └── resume.json        # Your resume data  <-- edit this
└── tests/                 # Unit tests (no AWS account needed)
```

## Prerequisites

- An AWS account and [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.12

## 1. Add your resume data

Edit `src/resume.json` with your own details (the file ships with placeholder data).

## 2. Run the tests (optional)

```bash
pip install -r requirements-dev.txt
python -m pytest tests -v
```

## 3. Deploy

```bash
sam build
sam deploy --guided      # first time; later just: sam deploy
```

The deploy creates the table, API, API key, usage plan and both Lambdas, then seeds the table from `src/resume.json`. The stack outputs show the API URL and API key ID.

## 4. Call the API

```bash
# Get the key value (replace <KEY_ID> with the ApiKeyId output)
aws apigateway get-api-key --api-key <KEY_ID> --include-value --query value --output text

# Call an endpoint
curl -H "x-api-key: <KEY_VALUE>" "<ApiUrl>/personal"
curl -H "x-api-key: <KEY_VALUE>" "<ApiUrl>/resume"
```

Without the header the API returns `403 Forbidden`. When the rate limit is exceeded it returns `429 Too Many Requests`. To see throttling, send a quick burst:

```bash
for i in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code}\n" -H "x-api-key: <KEY_VALUE>" "<ApiUrl>/skills"; done
```

## Security and throttling

- `ApiKeyRequired: true` is applied to every route.
- Usage plan defaults: 5 requests/second, burst of 10, 1000 requests/day. Change them with the `ThrottleRateLimit`, `ThrottleBurstLimit` and `DailyQuota` parameters.
- The API Lambda has read-only access to the one table (least privilege); only the seed Lambda can write.
- Error responses never expose internal details.

## Updating the data

Edit `src/resume.json`, then redeploy with a new value for the `DataVersion` parameter so the seed runs again (stale items are removed):

```bash
sam build && sam deploy --parameter-overrides DataVersion=2
```

## Clean up

```bash
sam delete
```
