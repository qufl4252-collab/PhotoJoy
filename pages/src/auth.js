import { initializeApp } from "firebase/app";
import {
  getAuth,
  setPersistence,
  browserSessionPersistence,
  onAuthStateChanged,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  sendPasswordResetEmail,
} from "firebase/auth";
import { firebaseConfig } from "./firebase-config.js";
import { Vault } from "./vault.js";
const configured = !!(
  firebaseConfig.apiKey &&
  firebaseConfig.projectId &&
  firebaseConfig.appId
);
const auth = configured ? getAuth(initializeApp(firebaseConfig)) : null;
if (auth) auth.languageCode = "ko";
const observers = new Set();
export const authReady = auth
  ? (async () => {
      await setPersistence(auth, browserSessionPersistence);
      await new Promise((resolve) => {
        const off = onAuthStateChanged(auth, () => {
          off();
          resolve();
        });
      });
    })()
  : Promise.resolve();
if (auth)
  onAuthStateChanged(auth, (user) => {
    for (const observe of observers) observe(user);
  });
export function onAccountChanged(callback) {
  observers.add(callback);
  return () => observers.delete(callback);
}
const fail = (message) => {
  throw new Error(message);
};
function requireAuth() {
  if (!auth?.currentUser) fail("로그인이 필요해요.");
  return auth.currentUser;
}
function vault() {
  const id = requireAuth().uid;
  return new Vault(id, () => auth?.currentUser?.uid === id);
}
function profile() {
  const user = requireAuth();
  return {
    user: {
      id: user.uid,
      display_name: user.displayName || user.email?.split("@")[0] || "사용자",
      platform: sessionStorage.getItem("photojoy-platform") || "windows",
    },
  };
}
function savePlatform(value) {
  if (!["windows", "android", "iphone"].includes(value))
    fail("접속 환경을 선택해 주세요.");
  sessionStorage.setItem("photojoy-platform", value);
}
const authMessages = {
  "auth/invalid-email": "아이디 칸에 올바른 이메일 주소를 입력해 주세요.",
  "auth/invalid-credential": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "auth/wrong-password": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "auth/user-not-found": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "auth/email-already-in-use":
    "이미 사용 중인 이메일입니다. 로그인하거나 비밀번호를 재설정하세요.",
  "auth/weak-password": "비밀번호를 10자 이상으로 만들어 주세요.",
  "auth/too-many-requests":
    "로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.",
  "auth/popup-closed-by-user": "Google 로그인 창이 닫혔습니다.",
  "auth/popup-blocked":
    "팝업이 차단되었습니다. 이 사이트의 팝업을 허용하고 다시 눌러주세요.",
  "auth/unauthorized-domain":
    "이 서비스 주소의 로그인 연결이 아직 완료되지 않았습니다.",
  "auth/operation-not-allowed":
    "해당 로그인 방법의 연결이 아직 완료되지 않았습니다.",
  "auth/network-request-failed":
    "로그인 서버에 연결할 수 없습니다. 네트워크를 확인하세요.",
};
function authError(error) {
  return new Error(
    authMessages[error.code] ||
      "로그인을 완료하지 못했어요. 잠시 후 다시 시도해 주세요.",
  );
}
export async function signInGoogle(platform) {
  if (!auth) fail("로그인 연결을 준비 중입니다.");
  savePlatform(platform);
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
    return profile();
  } catch (error) {
    throw authError(error);
  }
}
export async function resetPassword(email) {
  if (!auth) fail("로그인 연결을 준비 중입니다.");
  if (!email?.includes("@"))
    fail("아이디 칸에 가입한 이메일 주소를 먼저 입력해 주세요.");
  try {
    await sendPasswordResetEmail(auth, email.trim());
  } catch (error) {
    if (error.code !== "auth/user-not-found") throw authError(error);
  }
}

export function getVault() {
  return vault();
}
export function getSession() {
  return profile();
}
export async function logout() {
  await signOut(auth);
}
export async function login(email, password, platform, register = false) {
  await authReady;
  savePlatform(platform);
  if (register && password.length < 10)
    throw new Error("비밀번호는 10자 이상으로 입력하세요.");
  try {
    await (
      register ? createUserWithEmailAndPassword : signInWithEmailAndPassword
    )(auth, email.trim(), password);
    return profile();
  } catch (error) {
    throw authError(error);
  }
}
