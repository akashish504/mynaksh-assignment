import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    primary: { main: "#4b3f9e" },
    secondary: { main: "#b0732c" },
    background: { default: "#f6f5fb" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    button: { textTransform: "none", fontWeight: 600 },
  },
});
