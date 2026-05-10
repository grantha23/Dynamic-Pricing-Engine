# Dynamic Pricing Engine

A mini project that uses machine learning and real-time inputs to recommend product prices dynamically based on demand, competition, and market conditions.

## Overview

Traditional fixed pricing does not adapt quickly to changing demand. This project predicts pricing changes using historical pricing data, demand signals, and market behavior.

The system analyzes incoming data, applies a pricing model, and generates recommended prices that can help improve revenue and business decisions.

## Features

- Dynamic price prediction based on data patterns
- Machine learning based pricing model
- API service for predictions
- Dashboard for visualization and monitoring
- Dataset-driven training workflow
- Deployment-ready project structure
- Testing support

## Project Structure

```text
Dynamic-Pricing-Engine/
│
├── .streamlit/          # Streamlit configuration
├── Pricing-dataset/     # Pricing datasets
├── api/                 # FastAPI backend
├── dashboard/           # Dashboard application
├── data/                # Processed data
├── deployment/          # Deployment files
├── kafka/               # Streaming components
├── models/              # Trained models
├── tests/               # Test files
│
├── ml_training.py       # Model training script
├── inject_sidebar.py    # Dashboard helper
├── fix_encoding.py      # Encoding utility
└── README.md
