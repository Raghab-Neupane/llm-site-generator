# LLM Site Generator Backend

A professional, configurable, and portable backend for generating `llms.txt` knowledge bases from crawled sites.

---

## 1. Prerequisites & Installation

### Option A: Manual Installation
Install the required packages in your Python environment:
```bash
pip install python-dotenv mysql-connector-python fastapi uvicorn jose python-multipart beautifulsoup4 urllib3
```

### Option B: requirements.txt (if created)
```bash
pip install -r requirements.txt
```

---

## 2. Database Setup

### Step 1: Install MySQL Server
- **macOS**: Install via Homebrew:
  ```bash
  brew install mysql
  brew services start mysql
  ```
- **Windows**: Download and install the MySQL Installer from the [official portal](https://dev.mysql.com/downloads/installer/).
- **Linux**: Install via package manager:
  ```bash
  sudo apt update
  sudo apt install mysql-server
  sudo systemctl start mysql
  ```

### Step 2: Create the Database
Log into MySQL:
```bash
mysql -u root -p
```
Once logged in, run the following SQL command to create the database:
```sql
CREATE DATABASE llm_generator_db;
EXIT;
```

### Step 3: Import the Schema
Import the structure and initial tables using the provided [database.sql](file:///Users/raghabneupane/Documents/llm-site-generator/database.sql) file:
```bash
mysql -u root -p llm_generator_db < database.sql
```

---

## 3. Configuration Setup (.env)

The project uses environment variables to configure database connections safely.

1. Copy the example environment template:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your local database configuration details:
   ```env
   DB_HOST=localhost
   DB_USER=your_mysql_user
   DB_PASSWORD=your_mysql_password
   DB_NAME=llm_generator_db
   ```
   *(Note: For default local setups, `DB_USER` is usually `root` and `DB_PASSWORD` is blank/empty).*

---

## 4. Why "localhost" is Portable

Even though `DB_HOST` defaults to `localhost`, this setting is completely portable for other developers. 

- **Localhost Loopback**: `localhost` (IP address `127.0.0.1`) represents the local loopback interface. It points directly back to the physical computer running the application.
- When another developer clones this project and imports the database locally, their local MySQL server runs on their own machine. 
- When the backend connects to `localhost`, it connects to *their* local database instance, ensuring they don't need to change any hardcoded code to run the project.

---

## 5. Running the Backend

Start the development server with:
```bash
uvicorn app.main:app --reload
```
The server will watch for changes and run by default at `http://127.0.0.1:8000`.

---

## 6. Safe Error Handling
If the database configuration is incorrect or the database server is not running:
- The FastAPI application will still start successfully without crashing.
- A clean warning and failure details will be printed in the terminal.
- API endpoints requiring the database (like `/auth/login`) will return a clear JSON error response: `500 Database connection is currently unavailable`.
