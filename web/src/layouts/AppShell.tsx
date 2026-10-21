import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import IconButton from "@mui/material/IconButton";
import Toolbar from "@mui/material/Toolbar";
import { alpha } from "@mui/material/styles";
import { useState } from "react";
import { Outlet } from "react-router";
import UserMenu from "../features/auth/UserMenu";
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";
import ProjectSelect from "./ProjectSelect";
import SideNav, { drawerWidth } from "./SideNav";
import SideNavMobile from "./SideNavMobile";

/** The signed-in frame: topbar, permanent sidebar on md+, and the routed page. */
export default function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <Box sx={{ display: "flex" }}>
      <SideNav />
      <AppBar
        position="fixed"
        sx={{
          boxShadow: 0,
          bgcolor: "background.paper",
          backgroundImage: "none",
          borderBottom: "1px solid",
          borderColor: "divider",
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
        }}
      >
        <Toolbar sx={{ gap: 1 }}>
          {/* The hamburger is xs-only; the permanent sidebar takes over on md+. */}
          <IconButton
            aria-label="menu"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { xs: "inline-flex", md: "none" } }}
          >
            <MenuRoundedIcon />
          </IconButton>
          <ProjectSelect />
          <Box sx={{ flexGrow: 1 }} />
          <ColorModeIconDropdown />
          <UserMenu />
        </Toolbar>
      </AppBar>
      <SideNavMobile open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <Box
        component="main"
        sx={(theme) => ({
          flexGrow: 1,
          backgroundColor: theme.vars
            ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)`
            : alpha(theme.palette.background.default, 1),
          overflow: "auto",
        })}
      >
        {/* Spacer that keeps the content below the fixed topbar. */}
        <Toolbar />
        <Container maxWidth="lg" sx={{ pb: 6 }}>
          <Outlet />
        </Container>
      </Box>
    </Box>
  );
}
