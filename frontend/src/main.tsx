import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import './index.css'
import { startKeepAlive } from "./lib/keepAlive";

startKeepAlive(180_000);

const root = document.getElementById("root")!;
ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);