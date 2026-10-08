// The frame around every logged-in page: top bar with navigation, page below.

import AppBar from "@mui/material/AppBar";
import Button from "@mui/material/Button";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import styles from "./AppLayout.module.css";

const LINKS = [
  { to: "/chat", label: "Chat" },
  { to: "/memory", label: "Memory" },
  { to: "/profile", label: "Profile" },
];

export function AppLayout() {
  const { logout } = useAuth();

  return (
    <div className={styles.shell}>
      <AppBar position="static" elevation={0}>
        <Toolbar className={styles.toolbar}>
          <Typography variant="h6" component="span" className={styles.brand}>
            MyNaksh
          </Typography>
          <nav className={styles.nav}>
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <Button color="inherit" onClick={logout}>
            Log out
          </Button>
        </Toolbar>
      </AppBar>
      <main className={styles.page}>
        <Outlet />
      </main>
    </div>
  );
}
