import nuctest as nt
from quap import *
from tqdm import tqdm
from cProfile import Profile
from pstats import SortKey, Stats
from multiprocessing.pool import Pool

ident = ManyBodyBasisSpinIsospinOperator(nt.n_particles)
# list constructors make generating operators more streamlined
sig = [[ManyBodyBasisSpinIsospinOperator(nt.n_particles).sigma(i,a) for a in [0, 1, 2]] for i in range(nt.n_particles)]
tau = [[ManyBodyBasisSpinIsospinOperator(nt.n_particles).tau(i,a) for a in [0, 1, 2]] for i in range(nt.n_particles)]
# access like sig[particle][xyz]

# def g_pade_sig(dt, asig):
#     out = ManyBodyBasisSpinIsospinOperator(2).zeros()
#     for a in range(3):
#         for b in range(3):
#             out += asig[a, b] * sig[0][a] * sig[1][b]
#     out = -0.5 * dt * out
#     return out.exponentiate()


# def g_pade_sigtau(dt, asigtau):
#     out = ManyBodyBasisSpinIsospinOperator(2).zeros()
#     for a in range(3):
#         for b in range(3):
#             for c in range(3):
#                 out += asigtau[a, b] * sig[0][a] * sig[1][b] * tau[0][c] * tau[1][c]
#     out = -0.5 * dt * out
#     return out.exponentiate()


# def g_pade_tau(dt, atau):
#     out = ManyBodyBasisSpinIsospinOperator(2).zeros()
#     for c in range(3):
#         out += atau * tau[0][c] * tau[1][c]
#     out = -0.5 * dt * out
#     return out.exponentiate()


# def g_pade_coul(dt, v):
#     out = ident + tau[0][2] + tau[1][2] + tau[0][2] * tau[1][2]
#     out = -0.125 * v * dt * out
#     return out.exponentiate()


def g_pade_sig(dt, asig, i, j):
    out = ManyBodyBasisSpinIsospinOperator(nt.n_particles).zeros()
    for a in range(3):
        for b in range(3):
            out += asig[a, i, b, j] * sig[i][a] * sig[j][b]
    out = -0.5 * dt * out
    return out.exponentiate()


def g_pade_sigtau(dt, asigtau, i, j):
    out = ManyBodyBasisSpinIsospinOperator(nt.n_particles).zeros()
    for a in range(3):
        for b in range(3):
            for c in range(3):
                out += asigtau[a, i, b, j] * sig[i][a] * sig[j][b] * tau[i][c] * tau[j][c]
    out = -0.5 * dt * out
    return out.exponentiate()


def g_pade_tau(dt, atau, i, j):
    out = ManyBodyBasisSpinIsospinOperator(nt.n_particles).zeros()
    for c in range(3):
        out += atau[i, j] * tau[i][c] * tau[j][c]
    out = -0.5 * dt * out
    return out.exponentiate()


def g_pade_coul(dt, v, i, j):
    out = ident + tau[i][2] + tau[j][2] + tau[i][2] * tau[j][2]
    out = -0.125 * v[i, j] * dt * out
    return out.exponentiate()


def g_coulomb_onebody(dt, v, i):
    """just the one-body part of the expanded coulomb propagator
    for use along with auxiliary field propagators"""
    out = - 0.125 * v * dt * tau[i][2]
    return out.exponentiate()


def g_ls_linear(gls, i):
    # linear approx to LS
    out = ManyBodyBasisSpinIsospinOperator(nt.n_particles)
    for a in range(3):
        out = (ident - 1.j * gls[a, i] * sig[i][a]) * out 
    return out

def g_ls_onebody(gls_ai, i, a):
    # one-body part of the LS propagator factorization
    out = - 1.j * gls_ai * sig[i][a]
    return out.exponentiate()

def g_ls_twobody(gls_ai, gls_bj, i, j, a, b):
    # two-body part of the LS propagator factorization
    out = 0.5 * gls_ai * gls_bj * sig[i][a] * sig[j][b]
    return out.exponentiate()


def g_gauss_sample(dt, a, x, opi, opj):
    k = np.sqrt(-0.5 * dt * a, dtype=complex)
    norm = np.exp(0.5 * dt * a)
    gi = np.cosh(k * x) * ident + np.sinh(k * x) * opi
    gj = np.cosh(k * x) * ident + np.sinh(k * x) * opj
    return norm * gi * gj


def gauss_task(x, bra, ket, pot_dict, rng_mix=None):
    ket_p = ket.copy()
    ket_m = ket.copy()

    asig = pot_dict['asig']
    asigtau = pot_dict['asigtau']
    atau = pot_dict['atau']
    vcoul = pot_dict['vcoul']
    gls = pot_dict['gls']

    n = 0
    idx = [[0, 1, 2] for _ in range(9)]
    if rng_mix is not None: # no evidence that mixing helps.
        idx = rng_mix.choice(2, size=(9,3))
    for i,j in nt.pairs_ij:
        # SIGMA
        for a in idx[0]:
            for b in idx[1]:
                ket_p = g_gauss_sample(nt.dt, asig[a, i, b, j], x[n], sig[i][a], sig[j][b]) * ket_p
                ket_m = g_gauss_sample(nt.dt, asig[a, i, b, j], -x[n], sig[i][a], sig[j][b]) * ket_m
                n += 1
        # SIGMA TAU
        for a in idx[2]:
            for b in idx[3]:
                for c in idx[4]:
                    ket_p = g_gauss_sample(nt.dt, asigtau[a, i, b, j], x[n], sig[i][a] * tau[i][c], sig[j][b] * tau[j][c]) * ket_p
                    ket_m = g_gauss_sample(nt.dt, asigtau[a, i, b, j], -x[n], sig[i][a] * tau[i][c], sig[j][b] * tau[j][c]) * ket_m
                    n += 1
        # TAU
        for c in idx[5]:
            ket_p = g_gauss_sample(nt.dt, atau[i, j], x[n], tau[i][c], tau[j][c]) * ket_p
            ket_m = g_gauss_sample(nt.dt, atau[i, j], -x[n], tau[i][c], tau[j][c]) * ket_m
            n += 1

        # COULOMB
        ket_p = g_coulomb_onebody(nt.dt, vcoul[i, j], i) * g_coulomb_onebody(nt.dt, vcoul[i, j], j) * ket_p
        ket_m = g_coulomb_onebody(nt.dt, vcoul[i, j], i) * g_coulomb_onebody(nt.dt, vcoul[i, j], j) * ket_m
        ket_p = g_gauss_sample(nt.dt, 0.25 * vcoul[i, j], x[n], tau[i][2], tau[j][2]) * ket_p
        ket_m = g_gauss_sample(nt.dt, 0.25 * vcoul[i, j], -x[n], tau[i][2], tau[j][2]) * ket_m

    # LS
    for i in range(nt.n_particles):
        for a in range(3):
            ket_p = g_ls_onebody(gls[a, i], i, a) * ket_p
            ket_m = g_ls_onebody(gls[a, i], i, a) * ket_m
    for i,j in nt.pairs_ij:
        for a in range(3):
            for b in range(3):
                asigls = - gls[a, i]* gls[b, j]
                ket_p = g_gauss_sample(1, asigls, x[n], sig[i][a], sig[j][b]) * ket_p
                ket_m = g_gauss_sample(1, asigls, -x[n], sig[i][a], sig[j][b]) * ket_m
    trace_factor = cexp( 0.5 * np.sum(gls**2))
    ket_p = trace_factor * ket_p
    ket_m = trace_factor * ket_m
    
    return 0.5 * scalar(bra * ket_p + bra * ket_m)



def make_g_exact(pots):
    asig = pots['asig']
    asigtau = pots['asigtau']
    atau = pots['atau']
    vcoul = pots['vcoul']
    gls = pots['gls']

    # compute exact bracket
    g_exact = ident.copy()
    for i,j in nt.pairs_ij:
        g_exact = g_pade_sig(nt.dt, asig, i, j) * g_exact
        g_exact = g_pade_sigtau(nt.dt, asigtau, i, j) * g_exact 
        g_exact = g_pade_tau(nt.dt, atau, i, j) * g_exact
        g_exact = g_pade_coul(nt.dt, vcoul, i, j) * g_exact
    for i in range(nt.n_particles):
        g_exact = g_ls_linear(gls, i) * g_exact
    return g_exact



def gaussian_brackets_parallel(n_samples=100, mix=False, plot=False, disable_tqdm=False):
    print('HS brackets')
    bra, ket = nt.make_test_states()
    bra = bra.to_many_body_state()
    ket = ket.to_many_body_state()

    pot_dict = nt.make_all_potentials(rng=default_rng(seed=nt.global_seed))
    g_exact = make_g_exact(pot_dict)
    b_exact = bra * g_exact * ket

    n_aux = 9 + 27 + 3 + 1 + 3 + 9
    rng = default_rng(seed=nt.global_seed)
    x_set = rng.standard_normal((n_samples, n_aux))  # different x for each x,y,z
    with Pool(processes=nt.n_procs) as pool:
        b_array = pool.starmap_async(gauss_task, tqdm([(x, bra, ket, pot_dict) for x in x_set], disable=disable_tqdm, leave=True)).get()
    b_array = np.array(b_array)

    print(b_array)
    print(b_array.shape)

    if plot:
        nt.plot_samples(b_array, filename=f'hsprop_mb{nt.run_tag}.pdf', title='HS (MBB)')

    b_gauss = np.mean(b_array)
    s_gauss = np.std(b_array) / np.sqrt(n_samples)
    print('exact = ', b_exact)
    print(f'gauss = {b_gauss}  +/-  {s_gauss}')
    print('error = ', b_exact - b_gauss)
    print('square ratio = ', np.linalg.norm(b_exact/b_gauss) )


def g_rbm_sample(dt, a, h, opi, opj):
    norm = np.exp(-0.5 * dt * np.abs(a))
    W = np.arctanh(np.sqrt(np.tanh(0.5 * dt * np.abs(a))))
    arg = W * (2 * h - 1)
    qi = np.cosh(arg) * ident + np.sinh(arg) * opi
    qj = np.cosh(arg) * ident - np.sign(a) * np.sinh(arg) * opj
    return norm * qi * qj


def rbm_task(h, bra, ket, pot_dict):
    ket_p = ket.copy()
    ket_m = ket.copy()
    
    asig = pot_dict['asig']
    asigtau = pot_dict['asigtau']
    atau = pot_dict['atau']
    vcoul = pot_dict['vcoul']
    gls = pot_dict['gls']
    
    n = 0
    # SIGMA
    for a in [0, 1, 2]:
        for b in [0, 1, 2]:
            ket_p = g_rbm_sample(nt.dt, asig[a, b], h[n], sig[0][a], sig[1][b]) * ket_p
            ket_m = g_rbm_sample(nt.dt, asig[a, b], 1 - h[n], sig[0][a], sig[1][b]) * ket_m
            n += 1
    # SIGMA TAU
    for a in [0, 1, 2]:
        for b in [0, 1, 2]:
            for c in [0, 1, 2]:
                ket_p = g_rbm_sample(nt.dt, asigtau[a, b], h[n], sig[0][a] * tau[0][c], sig[1][b] * tau[1][c]) * ket_p
                ket_m = g_rbm_sample(nt.dt, asigtau[a, b], 1 - h[n], sig[0][a] * tau[0][c], sig[1][b] * tau[1][c]) * ket_m
                n += 1
    # TAU
    for c in [0, 1, 2]:
        ket_p = g_rbm_sample(nt.dt, atau, h[n], tau[0][c], tau[1][c]) * ket_p
        ket_m = g_rbm_sample(nt.dt, atau, 1 - h[n], tau[0][c], tau[1][c]) * ket_m
        n += 1
    # COULOMB
    ket_p = g_coulomb_onebody(nt.dt, vcoul) * g_rbm_sample(nt.dt, 0.25 * vcoul, h[n], tau[0][2], tau[1][2]) * ket_p
    ket_m = g_coulomb_onebody(nt.dt, vcoul) * g_rbm_sample(nt.dt, 0.25 * vcoul, 1 - h[n], tau[0][2], tau[1][2]) * ket_m
    # LS
    for i in range(nt.n_particles):
        for a in range(3):
            ket_p = g_ls_onebody(gls[a, i], i, a) * ket_p
            ket_m = g_ls_onebody(gls[a, i], i, a) * ket_m
    for i,j in nt.pairs_ij:
        for a in range(3):
            for b in range(3):
                asigls = - gls[a, i]* gls[b, j]
                ket_p = g_rbm_sample(1, asigls, h[n], sig[i][a], sig[j][b]) * ket_p
                ket_m = g_rbm_sample(1, asigls, 1 - h[n], sig[i][a], sig[j][b]) * ket_m
    trace_factor = cexp( 0.5 * np.sum(gls**2))
    ket_p = trace_factor * ket_p
    ket_m = trace_factor * ket_m

    return 0.5 * (bra * ket_p + bra * ket_m)


def rbm_brackets_parallel(n_samples=100, mix=False, plot=False, disable_tqdm=False):
    print('RBM brackets')
    bra, ket = nt.make_test_states()
    bra = bra.to_many_body_state()
    ket = ket.to_many_body_state()

    # compute exact bracket
    pot_dict = nt.make_all_potentials(rng=default_rng(seed=nt.global_seed))
    g_exact = make_g_exact(pot_dict)
    b_exact = bra * g_exact * ket

    # make population of identical wfns

    n_aux = 9 + 27 + 3 + 1 + 3 + 9
    rng = default_rng(seed=nt.global_seed)
    h_set = rng.integers(0, 2, size=(n_samples, n_aux))

    with Pool(processes=nt.n_procs) as pool:
        b_list = pool.starmap_async(rbm_task, tqdm([(h, bra, ket, pot_dict) for h in h_set], disable=disable_tqdm, leave=True)).get()
    

    if plot:
        nt.plot_samples(b_list, filename=f'rbmprop_mb{nt.run_tag}.pdf', title='RBM (MBB)')

    b_rbm = np.mean(b_list)
    s_rbm = np.std(b_list) / np.sqrt(n_samples)
    print('exact = ', b_exact)
    print(f'rbm = {b_rbm}  +/-  {s_rbm}')
    print('error = ', b_exact - b_rbm)


if __name__ == "__main__":
    plot = True
    disable_tqdm = False
    bra, ket = nt.make_test_states()
    bracket_t0 = bra * ket
    print(f'<G(t=0)> = {bracket_t0}')
    
    with Profile() as profile:
        gaussian_brackets_parallel(n_samples=nt.n_samples, plot=plot, disable_tqdm=disable_tqdm)
        # rbm_brackets_parallel(n_samples=nt.n_samples, plot=plot, disable_tqdm=disable_tqdm)
        # Stats(profile).strip_dirs().sort_stats(SortKey.CALLS).print_stats()
    print('DONE')