import Avatar from "@mui/material/Avatar";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListSubheader from "@mui/material/ListSubheader";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import { Navigate } from "react-router";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { logoutUser, selectUser } from "./authSlice";

/** The account dropdown: identity subheader plus sign-out. */
export default function UserMenu() {
  const dispatch = useAppDispatch();
  const user = useAppSelector(selectUser);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [pending, setPending] = useState(false);
  const [signedOut, setSignedOut] = useState(false);

  if (user === null) {
    // Guarded routes guarantee a session; render nothing rather than crash.
    return null;
  }
  if (signedOut) {
    return <Navigate to="/" replace />;
  }

  const initial = user.email.trim().charAt(0).toUpperCase() || "?";

  async function handleSignOut() {
    setAnchor(null);
    setPending(true);
    try {
      await dispatch(logoutUser()).unwrap();
    } finally {
      setPending(false);
      setSignedOut(true);
    }
  }

  return (
    <>
      <IconButton
        onClick={(event) => setAnchor(event.currentTarget)}
        aria-label="account menu"
        disabled={pending}
      >
        <Avatar sx={{ width: 32, height: 32, fontSize: 14, bgcolor: "primary.main" }}>
          {initial}
        </Avatar>
      </IconButton>
      <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
        <ListSubheader>{user.email}</ListSubheader>
        <Divider />
        <MenuItem onClick={handleSignOut} disabled={pending}>
          Sign out
        </MenuItem>
      </Menu>
    </>
  );
}
