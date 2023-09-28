import {createContext, useContext, useEffect, useState} from 'react';
import {useRouter} from 'next/router';

export const AccountContext = createContext();

export function useAccount() {
    return useContext(AccountContext);
}

export function AccountProvider({ children }) {
    const [accountId, setAccountId] = useState(null);
    const router = useRouter();

    useEffect(() => {
        // Only proceed if accountId is currently null
        if (accountId === null) {
            const { account_id } = router.query;

            // Set accountId state if it exists
            if (account_id) {
                console.log("setting account_id from url request params " + account_id)
                setAccountId(account_id);
            }
        }
    }, [router.query, accountId]);

    const value = {
        accountId,
        setAccountId
    };

    return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}