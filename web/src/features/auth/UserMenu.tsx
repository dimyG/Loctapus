import Avatar from "@mui/material/Avatar";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListSubheader from "@mui/material/ListSubheader";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { logoutUser, selectUser } from "./authSlice";

/** The account dropdown: identity subheader plus sign-out. */
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
    // Navigate before dispatching: the thunk clears the token, which the
    // RequireAuth guard would otherwise read as "bounced to /login". The
    // sign-out flow lands on the public landing (spec 6.2), and the thunk
    // never rejects (revocation is best-effort).
    navigate("/", { replace: true });
    void dispatch(logoutUser());
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
        <MenuItem onClick={handleSignOut}>Sign out</MenuItem>
      </Menu>
    </>
  );
}
