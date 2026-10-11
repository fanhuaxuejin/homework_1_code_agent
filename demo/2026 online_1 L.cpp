#include <bits/stdc++.h>
using namespace std;
#define ll long long
#define ull unsigned long long
#define ld long double
#define endl "\n"
chrono::_V2::system_clock::time_point bg_clock,en_clock;
const int N=5e5+10;
ll res=0;
int f[N];
int g[N];
int cunf[N];    
ll val[N]; 
bool added[N];
struct trie {
    int nex[N][26], cnt;
     // 该结点结尾的字符串是否存在
    void insert(string s) {  // 插入字符串
        int p = 0;
        int n = s.size();
        for (int i = 0; i < n; i++) {
            int c = s[i] - 'a';
            if (!nex[p][c]) {
            	nex[p][c] = ++cnt;  // 如果没有，就添加结点

            }
            p = nex[p][c];
            cunf[p]++;
            int cun=cunf[p];
            if(cun>g[i+1]){
            	if(added[cun]){
            		res -= val[cun];
            	}
            	f[cun]=i+1;
            	val[cun] = f[cun] ^ cun;
                res += val[cun];
                added[cun] = 1;
            	g[i+1]=cun;
            }
        }
    }
};
struct trie tr;
int main(){
	ios::sync_with_stdio(false);
    cin.tie(0);
    cout.tie(0);
    bg_clock=chrono::high_resolution_clock::now();
    //cout<<fixed<<setprecision(15);
	int T=1;
	// cin>>T;
	while(T--){
		int n;
		cin>>n;
		for(int i=1;i<=n;i++){
			string s;
			cin>>s;
			tr.insert(s);
			if (!added[i]) {
	            if (f[i] == 0) {
	                val[i] = (long long)i; // 0 ^ i
	            } else {
	                val[i] = (long long)f[i] ^ i;
	            }
	            res += val[i];
	            added[i] = 1;
	        }
			cout<<res<<endl;
		}
	}
	en_clock=chrono::high_resolution_clock::now();
    auto duration_clock=chrono::duration_cast<chrono::microseconds>(en_clock-bg_clock);
    double duration_count=duration_clock.count()*0.001;
    //cerr<<"Time:"<<duration_count<<"ms"<<endl;
	return 0;
}