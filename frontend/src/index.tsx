/**
 * AI Interview Feedback MVP - React Entry Point
 * 
 * This is the main entry point for the React application.
 * It renders the App component into the root DOM element.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { installAuthFetch } from './api/authFetch'
import './styles/main.css'

// Send the login token with every request to our API
installAuthFetch()

// Create root and render the application
ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
)
