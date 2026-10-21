import Avatar from "@mui/material/Avatar";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListItemText from "@mui/material/ListItemText";
import ListSubheader from "@mui/material/ListSubheader";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { logoutUser, selectUser } from "./authSlice";

/** The account dropdown: identity subheader, a future settings entry, and sign-out. */
export default function UserMenu() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const user = useAppSelector(selectUser);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  if (user === null) {
    // Guarded routes guarantee a session; render nothing rather than crash.
    return null;
  }

  const initial = user.email.trim().charAt(0).toUpperCase() || "?";

  function handleSignOut() {
    setAnchor(null);
    // Clear the session before navigating: logoutUser's synchronous section
    // (pending -> busy, sessionCleared -> user/token null) applies during the
    // dispatch call, so the landing can only ever render user=null and the
    // authed-visitor redirect cannot fire mid-sign-out. The thunk settles as
    // "signedout", so the guard routes home (never to /login) even if its
    // re-render interleaves with the navigation (spec 6.2).
    void dispatch(logoutUser());
    navigate("/", { replace: true });
  }

  return (
    <>
      <IconButton onClick={(event) => setAnchor(event.currentTarget)} aria-label="account menu">
        <Avatar sx={{ width: 32, height: 32, fontSize: 14, bgcolor: "primary.main" }}>
          {initial}
        </Avatar>
      </IconButton>
      <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
        <ListSubheader>{user.email}</ListSubheader>
        <Divider />
        {/* Settings is not built yet: disabled with a chip, never a dead link. */}
        <MenuItem disabled>
          <ListItemText primary="Settings" />
          <Chip label="Coming soon" size="small" />
        </MenuItem>
        <MenuItem onClick={handleSignOut}>Sign out</MenuItem>
      </Menu>
    </>
  );
}
