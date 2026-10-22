import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import MuiDrawer, { drawerClasses } from "@mui/material/Drawer";
import { styled } from "@mui/material/styles";
import BrandMark from "./BrandMark";
import NavMenuContent from "./NavMenuContent";

/** The permanent sidebar's width; the topbar offsets by it on md and up. */
export const drawerWidth = 240;

const Drawer = styled(MuiDrawer)({
  width: drawerWidth,
  flexShrink: 0,
  boxSizing: "border-box",
  [`& .${drawerClasses.paper}`]: {
    width: drawerWidth,
    boxSizing: "border-box",
  },
});

/** The permanent md+ sidebar: wordmark on top, the section nav below it. */
export default function SideNav() {
  return (
    <Drawer
      variant="permanent"
      sx={{
        display: { xs: "none", md: "block" },
        [`& .${drawerClasses.paper}`]: {
          backgroundColor: "background.paper",
        },
      }}
    >
      <Box sx={{ px: 2, py: 3 }}>
        <BrandMark />
      </Box>
      <Divider />
      <Box
        sx={{
          overflow: "auto",
          height: "100%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <NavMenuContent />
      </Box>
    </Drawer>
  );
}
