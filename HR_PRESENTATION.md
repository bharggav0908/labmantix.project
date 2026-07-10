# HR-Friendly Project Explanation

## Project in Simple Words

This project is an AI-based web application that helps developers review their code. Instead of waiting for a human reviewer, the system can analyze code, detect possible problems, and give useful feedback on quality, security, readability, and complexity.

In simple terms, it acts like a smart coding assistant that helps users improve their software before it goes live.

---

## Architecture Explained Layer by Layer

### 1. Frontend Layer
This is the part users see and interact with.

- Built with HTML, CSS, and Jinja templates
- Provides pages like login, signup, dashboard, review history, and report pages
- Lets users create projects, submit code, and view results

Why it is used:
- It makes the application easy to use and visually clear
- It gives a professional web experience without needing a heavy frontend framework

### 2. Backend Layer
This is the main logic layer of the application.

- Built with Python and FastAPI
- Handles user requests such as login, signup, creating projects, submitting code, and generating reviews
- Connects the frontend with the database and review logic

Why it is used:
- FastAPI is fast, simple, and easy to build APIs with
- Python is widely used in AI and automation projects

### 3. Application Logic Layer
This is where the smart review work happens.

- The system analyzes the submitted code
- It checks for common issues such as security concerns, bad structure, long lines, and maintainability issues
- It also creates a quality score and complexity report
- If OpenAI is configured, it can provide AI-based review suggestions

Why it is used:
- This layer gives the project its real value
- It turns the app from a simple website into an intelligent code review assistant

### 4. Data Layer
This is where user and review information is stored.

- Built using SQLite database
- Stores information such as:
  - users
  - projects
  - reviews
  - review findings

Why it is used:
- SQLite is lightweight and perfect for a local prototype or small-scale application
- It is easy to manage and suitable for demonstration purposes

### 5. Security Layer
This layer protects user accounts and data.

- Passwords are hashed using bcrypt
- Authentication is handled with JWT tokens
- User sessions are managed through secure cookies

Why it is used:
- It makes the application safer and more professional
- It shows that the project includes basic authentication and secure user handling

---

## Technologies Used

### Frontend Stack
- HTML
- CSS
- Jinja2 templates

### Backend Stack
- Python
- FastAPI
- Uvicorn

### Security Stack
- bcrypt
- PyJWT

### AI and Review Stack
- OpenAI API (optional)
- Rule-based heuristic review logic (built-in fallback)

### Database Stack
- SQLite

---

## Short HR-Ready Explanation

I built an AI-powered code review assistant that helps users review their source code automatically. The system has a clean frontend for user interaction, a backend server for handling requests, a review engine for analyzing code quality and security, and a database to store projects and review reports. I used Python, FastAPI, SQLite, JWT authentication, and OpenAI integration to build a practical and modern full-stack application.

---

## Very Simple Version for Interview or Presentation

This project is a smart web application that reviews code automatically. It helps users understand problems in their code, improves quality, and gives helpful suggestions. The project uses a frontend for user interaction, a backend for processing, a database for storing results, and AI-based logic for review analysis.
