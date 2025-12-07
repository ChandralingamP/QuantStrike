/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { Provider } from "react-redux";
import axios from "axios";
import App from "./App.jsx";
import { store } from "./app/store";
import { clearAuthUsername, setAuthUsername } from "./utils/authCookies.js";

vi.mock("axios");

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    clearAuthUsername();
  });

  it("renders home page header", async () => {
    axios.get.mockResolvedValueOnce({
      data: {
        client_id: "TRADER01",
        api_key_masked: "ABCD****WXYZ",
      },
    });

    setAuthUsername("TRADER01");

    render(
      <Provider store={store}>
        <App />
      </Provider>
    );

    expect(
      await screen.findByText(/Brokerage Connection Overview/i)
    ).toBeInTheDocument();
  });
});
