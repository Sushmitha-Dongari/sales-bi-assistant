# AI Development Reflection

## 1. AI Tools Used

Claude was used during the initial development of the project. ChatGPT was also used to help with project setup, troubleshooting, and preparing the GitHub submission.

## 2. How AI Assisted

AI assistance helped structure the application and develop its major components, including CSV ingestion, data validation, SQL analytics, question interpretation, the web interface, automated tests, and documentation.

The project was designed so that AI interprets a user's question but does not generate SQL queries or calculate business metrics. Instead, the application uses predefined analytics functions and database results to generate answers.

## 3. Problems Encountered

Several design and implementation challenges were addressed during development:

- **Data quality:** The application distinguishes rejected records from records that are stored but excluded from analytics.
- **Duplicate imports:** The CSV import process was designed to be idempotent, preventing previously imported records from being inserted again.
- **AI reliability:** The application uses Pydantic validation and a rule-based fallback when AI interpretation is unavailable or unsuccessful.
- **Data security:** Analytics use predefined, parameterised SQL queries and a read-only database connection.
- **Environment setup:** The project dependencies were installed locally, and the application was started successfully using Uvicorn.

## 4. Debugging and Testing

The application was tested locally using pytest. The test suite completed successfully with **55 tests passed in 3.65 seconds**.

The application was also started using Uvicorn, and requests to the web interface and the `/api/ask` endpoint returned successful HTTP responses during testing.

These checks helped verify the application's main functionality and provided confidence in the implementation.

## 5. Limitations and Future Improvements

Given another day of development, I would focus on the following improvements:

- Add category and date filters to support more detailed sales analysis.
- Use Decimal or integer minor units for more precise financial calculations.
- Improve the rule-based interpreter to support more variations in natural-language questions.
- Add authentication and authorisation.
- Introduce continuous integration to run automated tests whenever code changes.
- Test deployment configuration and deploy the application to a hosting platform.
- Improve error reporting and expand automated tests for edge cases.

## 6. Key Learning

This project demonstrated how natural-language interfaces can make business intelligence more accessible. It also reinforced the importance of validating AI output, separating interpretation from calculation, maintaining data quality, writing automated tests, and protecting database access.
