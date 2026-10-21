import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer, { drawerClasses } from "@mui/material/Drawer";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import NavMenuContent from "./NavMenuContent";

/** Props for the xs-only slide-in sidebar. */
type SideNavMobileProps = {
  /** Whether the drawer is open. */
  open: boolean;
  /** Called when the drawer should close: backdrop, escape, or a picked destination. */
  onClose: () => void;
};

/** The xs-only slide-in sidebar; choosing a destination closes it. */
export default function SideNavMobile({ open, onClose }: SideNavMobileProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        [`& .${drawerClasses.paper}`]: {
          backgroundImage: "none",
          backgroundColor: "background.paper",
        },
      }}
    >
      <Stack sx={{ maxWidth: "70dvw", height: "100%" }}>
        <Box sx={{ px: 2, py: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            RAG
          </Typography>
        </Box>
        <Divider />
        <Stack sx={{ flexGrow: 1 }}>
          <NavMenuContent onNavigate={onClose} />
        </Stack>
      </Stack>
    </Drawer>
  );
}
