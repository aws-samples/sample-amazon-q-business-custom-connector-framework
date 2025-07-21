Python and TypeScript/CDK Code Standards and Best Practices

Part 1: Python Standards

1. PEP 8 Compliance:
   - Adhere strictly to PEP 8 guidelines for code formatting.
   - Use 4 spaces for indentation (no tabs).
   - Limit lines to 120 characters maximum.

2. Naming Conventions:
   - Use descriptive, concise names for variables, functions, and classes.
   - Follow snake_case for variables and functions, PascalCase for classes.
   Example:
   ```python
   def calculate_total_revenue(monthly_sales: List[float]) -> float:
       return sum(monthly_sales)

   class RevenueAnalyzer:
       def __init__(self, data: Dict[str, float]):
           self.data = data
   ```

3. Type Annotations:
   - Always use type hints for function parameters and return values.
   - Use typing module for complex types.
   Example:
   ```python
   from typing import List, Dict, Optional

   def process_user_data(user_id: str, details: Dict[str, str]) -> Optional[User]:
       # Function implementation
   ```

4. List Comprehensions and Generator Expressions:
   - Use list comprehensions for simple list creation.
   - Prefer generator expressions for large datasets or when memory is a concern.
   Example:
   ```python
   # List comprehension
   squares = [x**2 for x in range(10)]

   # Generator expression
   large_dataset = (process(item) for item in get_large_dataset())
   ```

5. Leverage Built-in Functions and Libraries:
   - Utilize Python's built-in functions and standard library when possible.
   - Avoid reinventing the wheel.
   Example:
   ```python
   # Good: Using built-in functions
   numbers = [1, 2, 3, 4, 5]
   total = sum(numbers)
   maximum = max(numbers)

   # Avoid: Manual implementation or 3rd party libraries if there is an existing native function
   total = 0
   for num in numbers:
       total += num
   ```

6. DRY Principle (Don't Repeat Yourself):
   - Extract repeated code into functions or methods.
   - Use inheritance and composition to share common functionality.
   Example:
   ```python
   # Good: Reusable function
   def validate_input(value: str) -> bool:
       return value.strip() != ""

   # Usage
   if validate_input(user_name) and validate_input(user_email):
       process_user(user_name, user_email)
   ```

7. Virtual Environments:
   - Always use virtual environments for project isolation.
   - Use `venv` module for creating virtual environments.
   Example:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Unix or MacOS
   .venv\Scripts\activate.bat  # On Windows
   ```

8. Testing with pytest:
   - Write comprehensive unit tests using pytest.
   - Aim for at least 80% code coverage.
   - Mock only external dependencies or complex objects.
   Example:
   ```python
   import pytest
   from mymodule import calculate_total_revenue

   def test_calculate_total_revenue():
       assert calculate_total_revenue([100, 200, 300]) == 600
       assert calculate_total_revenue([]) == 0
       with pytest.raises(TypeError):
           calculate_total_revenue(None)
   ```

9. Comments and Docstrings:
   - Use meaningful comments to explain complex logic or decisions.
   - Write clear docstrings for all modules, classes, and functions.
   Example:
   ```python
   def calculate_compound_interest(principal: float, rate: float, time: int) -> float:
       """
       Calculate compound interest.

       Args:
           principal (float): Initial investment amount
           rate (float): Annual interest rate (in decimal form)
           time (int): Number of years

       Returns:
           float: The final amount after applying compound interest
       """
       return principal * (1 + rate) ** time
   ```

10. Exception Handling:
    - Use specific exception types.
    - Avoid bare except clauses.
    - Log exceptions with contextual information.
    Example:
    ```python
    import logging

    try:
        result = perform_operation(data)
    except ValueError as e:
        logging.error(f"Invalid data format: {e}")
        raise
    except IOError as e:
        logging.error(f"I/O error occurred: {e}")
        raise
    ```

11. Code Modularity:
    - Organize code into logical modules and packages.
    - Keep functions and classes focused on single responsibilities.
    Example:
    ```
    my_project/
    ├── data_processing/
    │   ├── __init__.py
    │   ├── cleaner.py
    │   └── transformer.py
    ├── analysis/
    │   ├── __init__.py
    │   └── statistical_analysis.py
    └── main.py
    ```

12. Data Modeling with Pydantic:
    - Use Pydantic (version 2 or greater) for data validation and settings management.
    Example:
    ```python
    from pydantic import BaseModel, Field

    class User(BaseModel):
        id: int
        name: str
        email: str = Field(..., regex=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
        age: int = Field(..., ge=0, le=120)
    ```

13. Function Parameter and Return Structure:
    - Use a single request object for multiple parameters.
    - Return a single response object.
    Example:
    ```python
    from pydantic import BaseModel

    class UserCreateRequest(BaseModel):
        name: str
        email: str
        age: int

    class UserCreateResponse(BaseModel):
        id: int
        success: bool

    def create_user(request: UserCreateRequest) -> UserCreateResponse:
        return UserCreateResponse(id=new_user_id, success=True)
    ```

14. Make Functions for Build and Test:
    - Use a Makefile for common tasks like setup, testing, and cleanup when available

Definition of Done:
- Minimum 80% code coverage in tests
- All code formatted using `make format`
- No linting errors or warnings (use `make lint`)
- All tests pass without errors or warnings


Part 2: TypeScript/CDK Standards

1. Strict Type Checking:
   - Enable strict type checking in your TypeScript configuration.
   - Use explicit type annotations for function parameters and return values.
   Example:
   ```typescript
   function processData(data: Record<string, number>): number[] {
     // Function implementation
   }
   ```

2. Consistent Coding Style:
   - Follow the Airbnb JavaScript Style Guide or your team's established conventions.
   - Use consistent naming conventions (camelCase for variables, PascalCase for types).
   Example:
   ```typescript
   interface UserProfile {
     userId: string;
     userName: string;
     email: string;
   }

   function fetchUserProfile(userId: string): Promise<UserProfile> {
     // Function implementation
   }
   ```

3. Destructuring and Spread Operator:
   - Utilize destructuring for cleaner and more readable code.
   - Use the spread operator to pass object or array properties as function arguments.
   Example:
   ```typescript
   const { name, email } = user;
   processUser({ ...user, age: 30 });
   ```

4. CDK Documentation:
   - Follow the TSDoc/JSDoc conventions for documenting CDK constructs.
   - Provide clear explanations of the infrastructure components, their configurations, and impacts.
   Example:
   ```typescript
   /**
    * Creates an Amazon S3 bucket with versioning and access logging.
    *
    * @param props - Configuration options for the S3 bucket
    * @returns The created S3 bucket
    */
   export function createS3Bucket(props: S3BucketProps): s3.Bucket {
     // Bucket creation implementation
   }
   ```

5. Complex Constructs:
   - Document the purpose and behavior of complex CDK constructs.
   - Explain any custom resource implementations or CloudFormation mappings.
   Example:
   ```typescript
   /**
    * Configures an API Gateway with Lambda integration and Cognito user pool authorization.
    *
    * Infrastructure components:
    * - API Gateway REST API with custom domain
    * - Lambda function integrated with the API
    * - Cognito user pool for authentication
    * - CloudWatch logging for the API and Lambda
    *
    * @param props - Configuration options for the API Gateway
    */
   export class ApiGatewayConstruct extends Construct {
     public readonly api: RestApi;

     constructor(scope: Construct, id: string, props: ApiGatewayProps) {
       super(scope, id);

       // API Gateway and other construct creation
     }
   }
   ```

Part 3: Project Structure

1. Separate Concerns:
   - Organize your codebase into logical modules and packages.
   - Group related files and functionality together.
   Example:
   ```
   my-project/
   ├── src/
   │   ├── api/
   │   │   ├── handlers.ts
   │   │   └── routes.ts
   │   ├── database/
   │   │   ├── models.ts
   │   │   └── repository.ts
   │   ├── utils/
   │   │   ├── logger.ts
   │   │   └── helpers.ts
   │   └── index.ts
   ├── tests/
   │   ├── api/
   │   │   ├── handlers.test.ts
   │   │   └── routes.test.ts
   │   ├── database/
   │   │   ├── models.test.ts
   │   │   └── repository.test.ts
   │   └── utils/
   │       ├── logger.test.ts
   │       └── helpers.test.ts
   ├── cdk/
   │   ├── lib/
   │   │   ├── api-stack.ts
   │   │   ├── database-stack.ts
   │   │   └── index.ts
   │   └── bin/
   │       └── cdk.ts
   ├── Makefile
   ├── package.json
   ├── tsconfig.json
   └── .eslintrc.js
   ```

3. CI/CD Integration:
   - Set up a CI/CD pipeline to automate build, test, and deployment.
   - Integrate code quality checks (linting, formatting, testing) into the pipeline.
   - Configure the pipeline to handle environment-specific configurations.

4. Documentation and Onboarding:
   - Create or maintain a a comprehensive README file with project overview, setup instructions, and contribution guidelines.
   - Provide code documentation, including module-level and function-level docstrings.
   - Create or maintain a developer onboarding guide for new team members.

5. Versioning and Dependencies:
   - Use semantic versioning for project and package versions.
   - Manage dependencies using a lockfile (e.g., `package-lock.json` or `yarn.lock`).
   - Regularly review and update dependencies to address security vulnerabilities and take advantage of new features.

Definition of Done:
- All code is formatted correctly (use `make format`)
- No linting errors or warnings (use `make lint`)
- All tests pass without errors or warnings (use `make test`)
- Minimum 80% code coverage in tests
- Clear and up-to-date project documentation

