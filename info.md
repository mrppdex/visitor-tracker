# Visitor Tracker Deployment Info

### Project Overview
A FastAPI application that tracks website visitors and stores data in a SQLite database.

### Local Structure
- `main.py`: FastAPI backend with `/track` and `/stats` endpoints.
- `Dockerfile`: Python 3.11-slim image configuration.
- `.github/workflows/deploy.yml`: Sliplane-specific GitHub Actions workflow.

### Deployment Instructions

#### 1. Push to GitHub
```bash
cd ../visitor-tracker
git init
git add .
git commit -m "Initial commit: Visitor Tracker"
git branch -M main
# Create a new repository on GitHub called 'visitor-tracker'
git remote add origin https://github.com/YOUR_USERNAME/visitor-tracker.git
git push -u origin main
```

#### 2. Configure GitHub Secrets
In your GitHub repo settings, add:
- `DEPLOY_SECRET`: The secret token provided by Sliplane.

#### 3. Update Workflow
In `.github/workflows/deploy.yml`, ensure you replace `your-service-id` with your actual Sliplane Service ID.

#### 4. Configure Sliplane
1. **Service Type**: Select "Docker Image".
2. **Image URL**: `ghcr.io/YOUR_USERNAME/visitor-tracker:latest`.
3. **Persistence**: Mount a Persistent Volume to `/app/data`.
4. **Port**: 8000.

#### 5. Usage
Add this to your website:
```html
<img src="https://your-sliplane-app-url.com/track?url=pawelpiela-blog" style="display:none;" />
```
View stats at: `https://your-sliplane-app-url.com/stats`
