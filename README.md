# Splitranch

Mobile app (Android first) to share expenses in groups with one running balance, plus an independent
"Quick splits" tool to split one-off bills with friends who don't use the app.

The repository holds the FastAPI API (`apps/api`), the Expo mobile app (`apps/mobile`), the shared
money domain (`packages/domain`) and the design docs below, which are the spec for business rules,
data model and API. Start at [docs/00-executive-summary.md](docs/00-executive-summary.md).

| Doc | Topic |
|---|---|
| [00](docs/00-executive-summary.md) | Executive summary, scope, key decisions, assumptions |
| [01](docs/01-architecture.md) | Architecture, layers, flows |
| [02](docs/02-data-model.md) | Data model, ERD, migrations, audit |
| [03](docs/03-business-rules.md) | Split engine, money algorithm, balance, payments, groups |
| [04](docs/04-api.md) | REST API |
| [05](docs/05-mobile-app.md) | Mobile app (Expo) |
| [06](docs/06-google-sheets.md) | Google Sheets export |
| [07](docs/07-future-ai.md) | Future AI phase |
| [08](docs/08-security-and-privacy.md) | Security, privacy, GDPR |
| [09](docs/09-testing-and-quality.md) | Testing, CI/CD, quality |
| [10](docs/10-roadmap.md) | Roadmap, tasks, acceptance criteria |
| [11](docs/11-repo-structure.md) | Monorepo layout, local dev |
| [12](docs/12-open-questions.md) | Open questions with default answers |
| [13](docs/13-design-system.md) | UI library decision and design system |
